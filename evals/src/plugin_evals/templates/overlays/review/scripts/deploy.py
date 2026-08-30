import subprocess

def deploy(target):
    subprocess.run("deploy.sh " + target, shell=True)
