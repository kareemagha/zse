import paramiko
import os
import time
import argparse
from dotenv import load_dotenv

load_dotenv()
ssh_client = paramiko.SSHClient()
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
private_key = paramiko.Ed25519Key(filename="C:/Users/eReuse/.ssh/id_ed25519")

try:
    ssh_client.connect(
        hostname="login.cse.unsw.edu.au",
        username="z5583960",
        pkey=private_key,
        password=os.getenv('cse_pass'),
        port=22
    )
    
    shell = ssh_client.invoke_shell()
    parser = argparse.ArgumentParser()
    
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose output")
    args = parser.parse_args()
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

finally:
    ssh_client.close()
