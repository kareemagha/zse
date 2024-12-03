import paramiko
import os
import sys
import os.path
import time
import argparse
import configparser
import shutil
from colorama import init, Fore
from platformdirs import user_config_dir

def main():
    init()
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--pipe', action='store_true', help='Creates a channel to send multiple commands via the same shell.')
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose output.")
    args = parser.parse_args()
    
    check_configs()
    ssh_connect(args)


# sets up SSH connection
def ssh_connect(args):
    config = configparser.ConfigParser(inline_comment_prefixes="#")
    
    config_file = os.path.join(user_config_dir("zse"), "config.ini")
    config.read(config_file)
    
    try:
        server_info = config["server"]
        auth_info = config["auth"]
    except:
        sys.stderr.write(Fore.RED + "Error: Reading authentication method failed" + Fore.RESET + "\n")
        exit(1)

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
            sys.stderr.write(Fore.RED + "Error: Cannot connect to CSE server. Review config file." + Fore.RESET + "\n")
            exit(1)
    elif auth_info["type"] == "password":
        try:
            ssh_client.connect(
                hostname=server_info["address"],
                username=server_info["username"],
                password=auth_info["password"],
                port=server_info["port"]
            )
        except:
            sys.stderr.write(Fore.RED + "Error: Cannot connect to CSE server. Review config file." + Fore.RESET + "\n")
            exit(1)
    else:
        return

    if args.pipe:
        ssh_mirror(ssh_client, args)
    
    ssh_client.close()

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



# acts like an SSH console
def ssh_mirror(ssh_client, args):
    shell = ssh_client.invoke_shell()
    if not args.verbose:
        shell.send("stty -echo\n")
        
    time.sleep(0.1)

    output = shell.recv(1024).decode()
    print(output, end="")

    while True:
        command = input("")
        if command.strip().lower() in {"exit", "quit"}:
            break
        elif command.strip().lower() in {"cls", "clear"}:
            os.system('cls')
        elif command.strip() == "":
            pass
        else: 
            shell.send(command + " --color=auto" + "\n")
            time.sleep(0.1)
            if shell.recv_ready():
                output = shell.recv(1024).decode()
                print(output, end="")
                
                
if __name__ == "__main__":
    main()