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
import time

remote_directory = ".zse/"

IGNORE_DIRS = ['.git']
IGNORE_PREFIXES = ['_', '.']


class error(Enum):
    connection = 0
    auth = 1
    


def main():
    init()
    parser = argparse.ArgumentParser(description="Process a command string.")
    parser.add_argument("command", help="The command to execute", nargs='+')
    parser.add_argument('-p', '--pipe', action='store_true', help='Creates a channel to send multiple commands via the same shell.')
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose output.")
    parser.add_argument('-d', '--dir', '--directory', type=str, help="Specifies the directory that will be copied to CSE machines.")
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

    # if args.pipe:
    #     ssh_mirror(ssh_client, args)
    
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
        exit(1)


def execute_user_command(ssh_client, args, command_str, config):
    print(command_str)
    
    stdin, stdout, stderr = ssh_client.exec_command(f"test -d {remote_directory}")
    exit_status = stdout.channel.recv_exit_status()
    
    if not exit_status == 0:
        ssh_client.exec_command(f"mkdir -m {700} -p {remote_directory}")
        if args.verbose:
            print(f"Directory '{remote_directory}' created with permissions {700}.")
        
    # sets up sftp to send files
    sftp = ssh_client.open_sftp()
    local_dir = args.dir if args.dir else "./"
    
    timestamp = time.strftime("%a %d %b %Y %H-%M-%S")
    remote_dir = os.path.join(remote_directory, timestamp)
    if args.verbose:
        print(f"Files will be uploaded to: {remote_dir}")
    
    sftp_recursive_put(sftp, local_path=local_dir, remote_path=remote_dir)    
    command = f'cd "{remote_dir}" && {" ".join(args.command)}'
    
    if args.verbose:
        print(f"Running command: {command}")
        
    time.sleep(0.1)
    stdin, stdout, stderr = ssh_client.exec_command(command)
    time.sleep(0.1)
    output = stdout.read().decode()
    error = stderr.read().decode()

    if output:
        print("Output:")
        print(output)
    if error:
        print("Error:")
        print(error)      
        
    ssh_client.close()
    if error:
        exit(1)
    else:
        exit(0)

def should_ignore(path):
    """Check if the directory or file should be ignored."""
    base_name = os.path.basename(path)
    if base_name in IGNORE_DIRS:
        return True
    if any(base_name.startswith(prefix) for prefix in IGNORE_PREFIXES):
        return True
    return False


def sftp_recursive_put(sftp, local_path, remote_path):
    if should_ignore(local_path):
        print(f"Ignoring: {local_path}")
        return
    
    if os.path.isdir(local_path):
        try:
            sftp.stat(remote_path)
        except FileNotFoundError:
            print(f"Creating remote directory: {remote_path}")
            sftp.mkdir(remote_path)

        for item in os.listdir(local_path):
            sftp_recursive_put(
                sftp,
                os.path.join(local_path, item),
                f"{remote_path}/{item}".replace("\\", "/")
            )
    else:
        print(f"Transferring file: {local_path} -> {remote_path}")
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
                if command.startswith(("ls", "grep", "diff", "vim")):
                    command += " --color=auto"
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
    
    exit(1)
    
    
if __name__ == "__main__":
    main()