import paramiko
import os
import sys
import os.path
import time
import argparse
import configparser
import shutil
from colorama import init, Fore, Style
from platformdirs import user_config_dir
from enum import Enum, auto

remote_directory = ".zse/"

IGNORE_DIRS = ['.git']
IGNORE_PREFIXES = ['_', '.']


class error(Enum):
    connection = 0
    auth = 1
    
class status(Enum):
    connecting = 0
    authenticating = 1
    sftp = 2
    syncing = 3
    sent = 4
    output = 5
    end_output = 6
    exit_stat = 7
    
    
def main():
    init()
    parser = argparse.ArgumentParser(description="Process a command string.")
    parser.add_argument("command", help="The command to execute", nargs='+')
    parser.add_argument('-p', '--pipe', action='store_true', help='Creates a channel to send multiple commands via the same shell.')
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose output.")
    parser.add_argument('-d', '--dir', '--directory', type=str, help="Specifies the directory that will be copied to CSE machines.")
    parser.add_argument('-c', '--clear', action='store_true', help="Clears remote zse folder before syncing files")
    args = parser.parse_args()
    
    check_configs()
    ssh_connect(args)


# Checks if config files have been setup
def check_configs():
    config_dir = user_config_dir("zse")
    file_name = "config.ini"
    file_path = os.path.join(config_dir, file_name)
    if not os.path.isfile(file_path):
        create_config()
    
    
def create_config():
    source_file = os.path.join(os.getcwd(), "config.ini")
    config_dir = user_config_dir("zse")
    os.makedirs(config_dir, exist_ok=True)
    try:
        shutil.copy(source_file, config_dir)
    except FileNotFoundError:
        print("Source file not found.")
    except PermissionError:
        print("Permission denied.")
    except Exception as e:
        print(f"An error occurred: {e}")


# sets up SSH connection
def ssh_connect(args):
    config = configparser.ConfigParser(inline_comment_prefixes="#")
    
    config_file = os.path.join(user_config_dir("zse"), "config.ini")
    config.read(config_file)
    
    try:
        server_info = config["server"]
        auth_info = config["auth"]
    except:
        print_err_msg(error.auth)

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    private_key = paramiko.Ed25519Key(filename=auth_info["private_key_path"])
    
    print_status(status.connecting, add=server_info["address"], port=server_info["port"])
    
    if auth_info["type"] == "key":
        try:
            ssh_client.connect(
                hostname=server_info["address"],
                username=server_info["username"],
                pkey=private_key,
                password=auth_info["password"],
                port=server_info["port"]
            )
        except:
            print_err_msg(error.connection)
    elif auth_info["type"] == "password":
        try:
            ssh_client.connect(
                hostname=server_info["address"],
                username=server_info["username"],
                password=auth_info["password"],
                port=server_info["port"]
            )
        except:
            print_err_msg(error.connection)
    else:
        return
    print_status(status.authenticating, zid=server_info["username"])
    read_command(args, ssh_client, config)
    
    ssh_client.close()


def read_command(args, ssh_client, config):
    command_str = ' '.join(args.command)
    try:
        if args.pipe:
            ssh_mirror(ssh_client, args, command_str)
        else:
            execute_user_command(ssh_client, args, command_str, config)
    except:
        sys.exit(1)


def execute_user_command(ssh_client, args, command_str, config):
    
    if args.clear:
        if args.verbose:
            print(f"Clearing remote directory {remote_directory}")
        stdin, stdout, stderr = ssh_client.exec_command(f"rm -r {remote_directory}")
        exit_code = stdout.channel.recv_exit_status()
        while exit_code != 0:
            if args.verbose:
                print(f"Command failed with exit code {exit_code}. Retrying...")
            stdin, stdout, stderr = ssh_client.exec_command(f"rm -r {remote_directory}")
            exit_code = stdout.channel.recv_exit_status()
    
    stdin, stdout, stderr = ssh_client.exec_command(f"test -d {remote_directory}")
    exit_status = stdout.channel.recv_exit_status()
    
    if not exit_status == 0:
        ssh_client.exec_command(f"mkdir -m {700} -p {remote_directory}")
        if args.verbose:
            print(f"Directory '{remote_directory}' created with permissions {700}.")
        
    # sets up sftp to send files
    print_status(status.sftp)
    sftp = ssh_client.open_sftp()
    local_dir = args.dir if args.dir else "./"
    
    timestamp = time.strftime("%a %d %b %Y %H-%M-%S")
    remote_dir = os.path.join(remote_directory, timestamp)
    if args.verbose:
        print(f"Files will be uploaded to: {remote_dir}")
        
    sftp_recursive_put(sftp, local_path=local_dir, remote_path=remote_dir, args = args)
    print_status(status.syncing)
    ssh_client.exec_command("export TERM=xterm-256color")    
    command = f'cd "{remote_dir}" && {" ".join(args.command)}'
    
    if args.verbose:
        print(f"Running command: {command}")
        
    print_status(status.sent, command=" ".join(args.command))
    print_status(status.output)
    stdin, stdout, stderr = ssh_client.exec_command(command, get_pty=True)

    # essentially just allows fro real time output from terminal

    for stdout_line in iter(stdout.readline, ""):
        if stdout_line:
            sys.stdout.write(stdout_line)
            sys.stdout.flush()
            
    for stderr_line in iter(stderr.readline, ""):
        if stderr_line:
            sys.stderr.write(stderr_line)
            sys.stderr.flush()

    exit_status = stdout.channel.recv_exit_status()
    print_status(status.end_output)
    print_status(status.exit_stat, exit=exit_status)


    ssh_client.close()
    exit(0)


def should_ignore(path):
    base_name = os.path.basename(path)
    if base_name in IGNORE_DIRS:
        return True
    if any(base_name.startswith(prefix) for prefix in IGNORE_PREFIXES):
        return True
    return False


def sftp_recursive_put(sftp, local_path, remote_path, args):
    if should_ignore(local_path):
        if args.verbose:
            print(f"Ignoring: {local_path}")
        return
    
    if os.path.isdir(local_path):
        try:
            sftp.stat(remote_path)
        except FileNotFoundError:
            if args.verbose:
                print(f"Creating remote directory: {remote_path}")
            sftp.mkdir(remote_path)

        for item in os.listdir(local_path):
            sftp_recursive_put(
                sftp,
                os.path.join(local_path, item),
                f"{remote_path}/{item}".replace("\\", "/"),
                args
            )
    else:
        loading_symbols = ["⠋", "⠙", "⠸", "⠴", "⠦", "⠇"]
        for i in range(len(loading_symbols) * 3):
            sys.stdout.write(
                f"\r\033[KSyncing file: {loading_symbols[i % len(loading_symbols)]} {local_path} -> {remote_path}"
            )
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write(f"\r\033[KTransferring file: {local_path} -> {remote_path}")
        sys.stdout.flush()
        sftp.put(local_path, remote_path)

# acts like an SSH console
def ssh_mirror(ssh_client, args, command_str):
    shell = ssh_client.invoke_shell()
    
    shell.send("export TERM=xterm-256color\n")
    
    if not args.verbose:
        shell.send("stty -echo\n")
        
    shell.send(command_str + "\n")
        
    sys.stdout.write(Fore.GREEN + 'Input "quit" or "exit" to exit out of shell.\n' + Fore.RESET)
    time.sleep(0.1)

    output = shell.recv(1024).decode()
    print(output, end="")
    
    while True:
        try:
            command = input("")
            if command.strip().lower() in {"exit", "quit"}:
                break
            elif command.strip().lower() in {"cls", "clear"}:
                os.system("cls" if os.name == "nt" else "clear")
            elif command.strip() == "":
                pass
            else: 
                shell.send(command + "\n")
                time.sleep(0.1)
                if shell.recv_ready():
                    output = shell.recv(10000).decode()
                    print(output, end="")
        except KeyboardInterrupt:
            print(Fore.RED + "\nConnection closed by user." + Style.RESET_ALL)
            ssh_client.close()
            sys.exit(0)
  

def print_err_msg(errno):
    if errno == error.connection:
        sys.stderr.write(Fore.RED + "Error: Cannot connect to CSE server. Review config file." + Fore.RESET + "\n")
    elif errno == error.auth:
        sys.stderr.write(Fore.RED + "Error: Reading authentication method failed." + Fore.RESET + "\n")
    
    sys.exit(1)
    
    
def print_status(status_num, command=None, add=None, port=None, zid=None, exit=None):
    if status_num == status.connecting:
        sys.stdout.write(
            f"\r\033[K\033\033[1;90m[1/5]\033[0m\tConnecting to: \033[3;36m{add}:\033[3;35m{port}\033\033[0m\n"
        )
    elif status_num == status.authenticating:
        sys.stdout.write(
            f"\r\033[K\033\033[1;90m[2/5]\033[0m\tAuthenticated as: \033[3;32m{zid}\033\033[0m\n"
        )
    elif status_num == status.sftp:
        sys.stdout.write(
            f"\r\033[K\033\033[1;90m[3/5]\033[0m\tEstablishing SFTP connection\033[0m\n"
        )
    elif status_num == status.syncing:
        sys.stdout.write(
            f"\r\033[K\033\033[1;90m[4/5]\033[0m\tSynced local files to remote\n"
        )
    elif status_num == status.sent:
        sys.stdout.write(
            f"\r\033[K\033[1;90m[5/5]\033[0m\tCommand sent: \033[33m{command}\033[0m\n"
        )
    elif status_num == status.output:
        sys.stdout.write(
            f"\033[1;35m=============== Output ===============\033[0m\n"
        )
    elif status_num == status.end_output:
        sys.stdout.write(
            f"\033[1;35m{'=' * 38}\033[0m\n"
        )
    elif status_num == status.exit_stat:
        if exit == 0:
            color = "32"  # Green
        else:
            color = "31"  # Red
        sys.stdout.write(
            f"\033[1;{color}mExit Status: {exit}\033[0m\n"
        )
    
    
if __name__ == "__main__":
    main()