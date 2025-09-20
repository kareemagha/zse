"""Progam that allows file upload to UNSW CSE machines
Useful for autotests and lab submissions
"""

import os
import secrets
import sys
import re
import shutil
import argparse
import stat
from enum import Enum
import configparser
import socket
import subprocess
import shlex
import time
from platformdirs import user_config_dir
import paramiko
from paramiko import (
    AuthenticationException,
    SSHException,
)
from colorama import init, Fore, Style

REMOTE_DIR = ".zse/"
IGNORE_DIRS = [".git"]
IGNORE_PREFIXES = ["_", "."]
VERSION_NO = "1.5.0"


class Error(Enum):
    """Enum for error types"""

    CONNECTION = 0
    AUTH = 1
    EMPTY = 2
    REMOVAL = 3


class Status(Enum):
    """Enum for satus types"""

    CONNECTING = 0
    AUTHENTICATING = 1
    SFTP = 2
    SYNCING = 3
    SENT = 4
    OUTPUT = 5
    END_OUTPUT = 6
    EXIT_STAT = 7


def main():
    """Main function for program"""
    init()  # initialises colourama
    args = setup_argparse()
    check_configs()
    ssh_connect(args)
    sys.exit(0)


def setup_argparse():
    """Setups argparse to read and output the result of arguments"""
    parser = argparse.ArgumentParser(
        description="CLI tool that allows UNSW students to submit work to CSE machines."
    )
    parser.add_argument("command", help="The command to execute", nargs="+")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Uploads to a tempdir then opens a real ssh -t session:\n"
        '  ssh -t ZID@host "cd <tempdir> && <command> && bash; rm -rf <tempdir>"',
    )
    parser.add_argument("-V", "--version", action="version", version=VERSION_NO)
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output."
    )
    parser.add_argument(
        "-d",
        "--dir",
        "--directory",
        type=str,
        help="Specifies the directory that will be copied to CSE machines.",
    )
    parser.add_argument(
        "-c",
        "--clear",
        action="store_true",
        help="Clears remote zse folder before syncing files",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force file syncing, overwriting existing files without user input",
    )
    parser.add_argument(
        "-l",
        "--local",
        type=str,
        help="Downloads files from remote server. Useful for fetch commands.",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        nargs="?",
        const="./",
        type=str,
        help="Excludes folders/files from syncing (default is './' if no value is provided)",
    )
    args = parser.parse_args()

    return args


def check_configs():
    """Checks if a config file has been setup"""
    config_dir = user_config_dir("zse")
    file_name = "config.ini"
    file_path = os.path.join(config_dir, file_name)
    if not os.path.isfile(file_path):
        create_config()


def create_config():
    """Creates a config file if it doesn't exist, either by copying or generating one."""
    config_dir = user_config_dir("zse")
    os.makedirs(config_dir, exist_ok=True)
    config_file_path = os.path.join(config_dir, "config.ini")

    if not os.path.exists(config_file_path):
        config_content = """
[server]
address = login.cse.unsw.edu.au # no need to change
port = 22 # no need to change
username = z5555555 # your zID

# note: dont use quotation marks around anything!

[auth] # password auth
type = password # do not change
password =  # optional (but recommended)

; [auth] # key auth
; type = key # do not change
; private_key_path = ~/.ssh/id_ed25519 # required for key auth
; passphrase = # optional if you have set a passphrase
; password = # optional if you havent created a keypair
        """
        try:
            with open(config_file_path, "w", encoding="utf-8") as config_file:
                config_file.write(config_content.strip())
                print("\033[32mConfig file created successfully.\033[0m\n")
                print("Edit this file to use zse:")
                print(f"{config_file_path}")
                sys.exit(0)
        except (OSError, IOError) as e:
            print(f"\033[31mError creating config file: {e}\033[0m")
            print("Edit this file to use zse:")
            print(f"{config_file_path}")
            sys.exit(0)


def ssh_connect(args):
    """Sets up SSH connection"""
    config = configparser.ConfigParser(inline_comment_prefixes="#")

    config_file = os.path.join(user_config_dir("zse"), "config.ini")
    config.read(config_file)

    try:
        server_info = config["server"]
        auth_info = config["auth"]
    except (KeyError, TypeError, ValueError):
        print_err_msg(Error.AUTH)

    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print_status(
            Status.CONNECTING, add=server_info["address"], port=server_info["port"]
        )
    except (KeyError, TypeError, ValueError) as config_err:
        print(config_err)
        print_err_msg(Error.EMPTY)

    if auth_info["type"] == "key":
        try:
            ssh_client.connect(
                hostname=server_info["address"],
                username=server_info["username"],
                pkey=paramiko.Ed25519Key(filename=auth_info["private_key_path"]),
                passphrase=auth_info["passphrase"],
                password=auth_info["password"],
                port=int(server_info.get("port", 22)),
            )
        except (
            AuthenticationException,
            SSHException,
            socket.error,
            socket.timeout,
            KeyboardInterrupt,
        ) as e:
            print(e)
            print_err_msg(Error.CONNECTION)
    elif auth_info["type"] == "password":
        try:
            if (auth_info["password"]) == "":
                password_var = input("What is your password: ")
            else:
                password_var = auth_info["password"]

            ssh_client.connect(
                hostname=server_info["address"],
                username=server_info["username"],
                password=password_var,
                port=int(server_info.get("port", 22)),
                look_for_keys=False,
            )
        except (
            AuthenticationException,
            SSHException,
            socket.error,
            socket.timeout,
            KeyboardInterrupt,
        ) as e:
            print(e)
            print_err_msg(Error.CONNECTION)
    else:
        print_err_msg(Error.EMPTY)
    print_status(Status.AUTHENTICATING, zid=server_info["username"])
    read_command(args, ssh_client)

    ssh_client.close()


def read_command(args, ssh_client):
    """Reads the user command, and directs to correct function"""
    try:
        execute_user_command(ssh_client, args)
    except (
        SSHException,
        IOError,
        OSError,
        subprocess.CalledProcessError,
        KeyboardInterrupt,
    ):
        sys.exit(1)


def execute_user_command(ssh_client, args, s=None):
    """Executes the user's command in the remote shell (for non pipe option)"""
    if args.clear:
        if args.verbose:
            print(f"Clearing remote directory {REMOTE_DIR}")
        _stdin, stdout, _stderr = ssh_client.exec_command(f"rm -r {REMOTE_DIR}")
        exit_code = stdout.channel.recv_exit_status()
        while exit_code != 0:
            try:
                if args.verbose:
                    print(f"Command failed with exit code {exit_code}. Retrying...")
                _stdin, stdout, _stderr = ssh_client.exec_command(f"rm -r {REMOTE_DIR}")
                exit_code = stdout.channel.recv_exit_status()
            except KeyboardInterrupt:
                print_err_msg(Error.REMOVAL)

    _stdin, stdout, _stderr = ssh_client.exec_command(f"test -d {REMOTE_DIR}")
    exit_status = stdout.channel.recv_exit_status()

    if not exit_status == 0:
        ssh_client.exec_command(f"mkdir -m {700} -p {REMOTE_DIR}")
        if args.verbose:
            print(f"Directory '{REMOTE_DIR}' created with permissions {700}.")

    print_status(Status.SFTP)
    sftp = ssh_client.open_sftp()
    local_dir = args.dir if args.dir else "./"

    remote_dir = os.path.join(REMOTE_DIR, secrets.token_hex(4))

    if args.local:
        run_and_download(sftp, remote_dir, ssh_client, args)
    else:
        upload_and_run(sftp, local_dir, remote_dir, ssh_client, args)


def upload_and_run(sftp, local_dir, remote_dir, ssh_client, args, *, s=None):
    """Uploads local files and runs user command"""
    if args.verbose:
        print(f"Files will be uploaded to: {remote_dir}")

    sftp.mkdir(remote_dir)
    sftp_recursive_put(sftp, local_path=local_dir, remote_path=remote_dir, args=args)
    print_status(Status.SYNCING)

    if not args.interactive:
        ssh_client.exec_command("export TERM=xterm-256color")
        give_bypassed_user_cmd = (
            ("yes | " + " ".join(args.command))
            if args.command[0].split()[0]
            in ("give",)  # add more stuff to auto bypass if needed
            else " ".join(args.command)
        )
        command = f'cd "{remote_dir}" && {give_bypassed_user_cmd}'
        if args.verbose:
            print(f"Running command: {command}")
        print_status(Status.SENT, command=" ".join(args.command))
        print_status(Status.OUTPUT)

        _stdin, stdout, stderr = ssh_client.exec_command(command, get_pty=True)
        try:
            read_terminal(stdout, stderr)
        except KeyboardInterrupt:
            pass

        ssh_client.exec_command(f"rm -rf ~/{shlex.quote(remote_dir)}")
        if args.verbose:
            print(f"Cleared remote directory {remote_dir}")

        ssh_client.close()
        sys.exit(0)

    # --- New -p behavior: system ssh -t session ---
    try:
        sftp.close()
    except Exception:
        pass
    try:
        ssh_client.close()
    except Exception:
        pass

    config = configparser.ConfigParser(inline_comment_prefixes="#")
    config_file = os.path.join(user_config_dir("zse"), "config.ini")
    config.read(config_file)
    server_info = config["server"]
    auth_info = config["auth"]

    user = server_info["username"]
    host = server_info["address"]
    port = str(server_info.getint("port", fallback=22))

    remote_cmd = (
        shlex.join(["cd", remote_dir])  # cd into temp dir
        + (
            (" && " + " ".join(args.command)) if args.command else ""
        )  # run user command
        + "; bash; "  # launch shell
        + " ".join(["rm", "-rf", "~/" + shlex.quote(remote_dir)])  # delete temp dir
    )
    # print("Remote cmd:", remote_cmd)

    ssh_cmd = ["ssh", "-t", "-p", port, f"{user}@{host}", remote_cmd]

    pw = auth_info.get("password", "").strip()
    if auth_info.get("type", "password") == "password" and pw:
        if shutil.which("sshpass"):
            ssh_cmd = ["sshpass", "-p", pw] + ssh_cmd
        elif args.verbose:
            print(
                "sshpass not found; falling back to interactive SSH prompt. "
                "Tip: install sshpass or use key auth in config.ini."
            )

    if args.verbose:
        print(f"Launching interactive session: {' '.join(ssh_cmd)}")

    print_status(Status.SENT, command=" ".join(args.command))
    print_status(Status.OUTPUT)

    proc = subprocess.Popen(ssh_cmd, stdin=None, stdout=None, stderr=None)
    rc = proc.wait()

    print_status(Status.END_OUTPUT)
    print_status(Status.EXIT_STAT, exit_stat=rc)
    sys.exit(rc)


def run_and_download(sftp, remote_dir, ssh_client, args):
    """Runs remote command and downloads files from dir"""

    sftp.mkdir(remote_dir)
    ssh_client.exec_command("export TERM=xterm-256color")
    command = f'cd "{remote_dir}" && {" ".join(args.command)}'
    print_status(Status.SENT, command=" ".join(args.command))
    _stdin, stdout, stderr = ssh_client.exec_command(command, get_pty=True)

    if args.local:
        local_dir = args.local
    else:
        local_dir = "./"

    print_status(Status.OUTPUT)
    try:
        read_terminal(stdout, stderr)
    except KeyboardInterrupt:
        pass
    download_dir(sftp, remote_dir, local_dir, args)
    ssh_client.exec_command(f"rm -rf ~/{shlex.quote(remote_dir)}")
    if args.verbose:
        print(f"Cleared remote directory {remote_dir}")

    sys.exit(0)


def read_terminal(stdout, stderr):
    """
    Stream stdout/stderr in (semi) real-time without blocking forever on readline().
    Interleaves both streams and allows KeyboardInterrupt to be raised promptly.
    """
    chan = stdout.channel  # same channel backs both stdout/stderr
    chan.settimeout(0.1)  # short timeout makes the loop interruptible

    try:
        while True:
            try:
                if chan.recv_ready():
                    sys.stdout.buffer.write(chan.recv(4096))
                    sys.stdout.flush()
                if chan.recv_stderr_ready():
                    sys.stderr.buffer.write(chan.recv_stderr(4096))
                    sys.stderr.flush()
            except socket.timeout:
                pass  # just poll again

            if chan.exit_status_ready():
                break

            time.sleep(0.03)  # keep CPU calm
    finally:
        print()
        print_status(Status.END_OUTPUT)
        chan.send("\x03")  # Ctrl c
        chan.send("\x04")  # Ctrl d

        # print("Sent CTRL-C to server")
        # Send CTRL-C to the server so we dont have infinite loop if server is in a loop.
        exit_status = chan.recv_exit_status()

        print_status(Status.EXIT_STAT, exit_stat=exit_status)


def download_dir(sftp, remote_path, local_path, args):
    """Recursively download remote directories and their files."""
    try:
        os.makedirs(local_path, exist_ok=True)

        for item in sftp.listdir_attr(remote_path):
            remote_item_path = f"{remote_path}/{item.filename}"
            local_item_path = os.path.join(local_path, item.filename)

            if stat.S_ISDIR(item.st_mode):
                if args.verbose:
                    print(f"Entering directory: {remote_item_path}")
                download_dir(sftp, remote_item_path, local_item_path, args)

                if args.clear:
                    sftp.rmdir(remote_item_path)
                    if args.verbose:
                        print(f"Deleted remote directory: {remote_item_path}")
            else:
                handle_file(sftp, item, remote_item_path, local_item_path, args)
    except KeyboardInterrupt:
        print(Fore.RED + "\nConnection closed by user." + Style.RESET_ALL)
        sys.exit(0)


def handle_file(sftp, item, remote_item_path, local_item_path, args):
    """Handles downloading a single file and optionally clearing it."""
    if args.verbose:
        print(f"Processing file: {remote_item_path}")

    if os.path.isfile(local_item_path) and not args.force:
        user_input = input(
            f"{item.filename} already exists. Replace it? (y/n): "
        ).lower()
        if user_input not in ["y", "yes"]:
            if args.verbose:
                print(f"Skipped: {remote_item_path}")
            return

    sftp.get(remote_item_path, local_item_path)
    if args.verbose:
        print(f"Downloaded: {remote_item_path} to {local_item_path}")

    if args.clear:
        sftp.remove(remote_item_path)
        if args.verbose:
            print(f"Deleted remote file: {remote_item_path}")


def should_ignore(path, args):
    """Helper function to determine what files/folders to ignore when syncing"""
    base_name = os.path.basename(path)
    ignored_files = IGNORE_DIRS
    if args.exclude:
        try:
            ignored_files = re.split(r"[,\s]+", args.exclude.strip())
        except (KeyError, TypeError, ValueError):
            return True
    if base_name in IGNORE_DIRS or path in ignored_files:
        return True
    if any(base_name.startswith(prefix) for prefix in IGNORE_PREFIXES):
        return True
    return False


def sftp_recursive_put(sftp, local_path, remote_path, args):
    """Recursively looks through directories to find files to sync"""
    try:
        if should_ignore(local_path, args):
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
                    args,
                )
        else:
            loading_symbols = ["⠋", "⠙", "⠸", "⠴", "⠦", "⠇"]
            for i in range(len(loading_symbols) * 3):
                terminal_length = shutil.get_terminal_size().columns
                print(
                    f"\r\033[KSyncing file: "
                    f"{loading_symbols[i % len(loading_symbols)]} "
                    f"{local_path} -> "
                    f"{remote_path}"[:terminal_length],
                    flush=True,
                    end="",
                )
            print(
                f"\r\033[KTransferring file: {local_path} -> {remote_path}"[
                    :terminal_length
                ],
                flush=True,
                end="",
            )
            sftp.put(local_path, remote_path)
    except KeyboardInterrupt:
        print(Fore.RED + "\nConnection closed by user." + Style.RESET_ALL)
        sys.exit(0)


def print_err_msg(errno):
    """Helper function that prints error messages"""
    config_dir = str(user_config_dir("zse"))
    if errno == Error.CONNECTION:
        sys.stderr.write(
            f"{Fore.RED}"
            + "Error: Cannot connect to CSE server. Review config file @ "
            + f"{config_dir}."
            + f"{Fore.RESET}\n"
        )
    elif errno == Error.AUTH:
        sys.stderr.write(
            Fore.RED
            + "Error: Reading authentication method failed."
            + Fore.RESET
            + "\n"
        )
    elif errno == Error.EMPTY:
        sys.stderr.write(
            f"{Fore.RED}"
            + "Error: Reading config.ini failed. Review config file @ "
            + f"{config_dir}"
            + f"{Fore.RESET}"
        )
    elif Error.REMOVAL:
        sys.stderr.write(
            f"{Fore.RED}"
            + "Error: Cannot delete remote directory. Please review file permissions."
            + f"{Fore.RESET}"
        )
    sys.exit(1)


def create_status_printer():
    """Helper function to generate satus messages"""
    counter = 0

    def _print_status(status_num, **kwargs):
        nonlocal counter

        non_increment = {Status.OUTPUT, Status.END_OUTPUT, Status.EXIT_STAT}

        if status_num not in non_increment:
            counter += 1
            total_steps = 5
            sys.stdout.write(f"\r\033[K\033[1;90m[{counter}/{total_steps}]\033[0m\t")

        command = kwargs.get("command")
        add = kwargs.get("add")
        port = kwargs.get("port")
        zid = kwargs.get("zid")
        exit_stat = kwargs.get("exit_stat")

        if status_num == Status.CONNECTING:
            sys.stdout.write(
                f"Connecting to: \033[3;36m{add}:\033[3;35m{port}\033[0m\n"
            )
        elif status_num == Status.AUTHENTICATING:
            sys.stdout.write(f"Authenticated as: \033[3;32m{zid}\033[0m\n")
        elif status_num == Status.SFTP:
            sys.stdout.write("Establishing SFTP connection\033[0m\n")
        elif status_num == Status.SYNCING:
            sys.stdout.write("Synced local files to remote\n")
        elif status_num == Status.SENT:
            sys.stdout.write(f"Command sent: \033[33m{command}\033[0m\n")
        elif status_num == Status.OUTPUT:
            sys.stdout.write(
                "\033[1;35m=============== Output ===============\033[0m\n"
            )
        elif status_num == Status.END_OUTPUT:
            sys.stdout.write(f"\033[1;35m{'=' * 38}\033[0m\n")
        elif status_num == Status.EXIT_STAT:
            colour = "32" if exit_stat == 0 else "31"
            sys.stdout.write(f"\033[1;{colour}mExit status: {exit_stat}\033[0m\n")

    return _print_status


print_status = create_status_printer()

if __name__ == "__main__":
    main()
