import os
import sys
import subprocess
from copy import deepcopy
import socket
import psutil
from tempfile import mkstemp
# make sure we have jupyter in the auto requirements
import jupyter
from trains import Task

# set default docker image, with network configuration
os.environ['TRAINS_DOCKER_IMAGE'] = 'nvidia/cuda --network host'

# initialize TRAINS
task = Task.init(project_name='examples', task_name='Remote Jupyter NoteBook')

# get rid of all the runtime TRAINS
preserve = ('TRAINS_API_HOST', 'TRAINS_WEB_HOST', 'TRAINS_FILES_HOST', 'TRAINS_CONFIG_FILE',
            'TRAINS_API_ACCESS_KEY', 'TRAINS_API_SECRET_KEY', 'TRAINS_API_HOST_VERIFY_CERT')

# setup os environment
env = deepcopy(os.environ)
for key in os.environ:
    if key.startswith('TRAINS') and key not in preserve:
        env.pop(key, None)

# Add jupyter server base folder
param = {
    'jupyter_server_base_directory': '~/',
    'ssh_server': True,
    'ssh_password': 'training'
}
task.connect(param)

try:
    hostname = socket.gethostname()
    hostnames = socket.gethostbyname(socket.gethostname())
except Exception:
    def get_ip_addresses(family):
        for interface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family == family:
                    yield snic.address

    hostnames = list(get_ip_addresses(socket.AF_INET))
    hostname = hostnames[0]

if param.get('ssh_server'):
    print('Installing SSH Server on {} [{}]'.format(hostname, hostnames))
    ssh_password = param.get('ssh_password', 'training')
    try:
        used_ports = [i.laddr.port for i in psutil.net_connections()]
        port = [i for i in range(10022, 15000) if i not in used_ports][0]

        result = os.system(
            'apt-get install -y openssh-server && '
            'mkdir -p /var/run/sshd && '
            'echo \'root:{password}\' | chpasswd && '
            'echo \'PermitRootLogin yes\' >> /etc/ssh/sshd_config && '
            'sed -i \'s/PermitRootLogin prohibit-password/PermitRootLogin yes/\' /etc/ssh/sshd_config && '
            'sed \'s@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g\' -i /etc/pam.d/sshd && '
            'echo "export VISIBLE=now" >> /etc/profile && '
            'echo "export TRAINS_CONFIG_FILE={trains_config_file}" >> /etc/profile && '
            '/usr/sbin/sshd -p {port}'.format(
                password=ssh_password, port=port, trains_config_file=os.environ.get('TRAINS_CONFIG_FILE')))

        if result == 0:
            print('\n#\n# SSH Server running on {} [{}] port {}\n# LOGIN u:root p:{}\n#\n'.format(
                hostname, hostnames, port, ssh_password))
        else:
            raise ValueError()
    except:
        print('\n#\n# Error: SSH server could not be launched\n#\n')

# execute jupyter notebook
fd, local_filename = mkstemp()
cwd = os.path.expandvars(os.path.expanduser(param['jupyter_server_base_directory'])) \
    if param['jupyter_server_base_directory'] else os.getcwd()
print('Running Jupyter Notebook Server on {} [{}] at {}'.format(hostname, hostnames, cwd))
process = subprocess.Popen([sys.executable, '-m', 'jupyter', 'notebook', '--no-browser', '--allow-root', '--ip', '0.0.0.0'],
                           env=env, stdout=fd, stderr=fd, cwd=cwd)

# print stdout/stderr
prev_line_count = 0
process_running = True
while process_running:
    process_running = False
    try:
        process.wait(timeout=2.0 if prev_line_count == 0 else 15.0)
    except subprocess.TimeoutExpired:
        process_running = True

    with open(local_filename, "rt") as f:
        # read new lines
        new_lines = f.readlines()
        if not new_lines:
            continue
        output = ''.join(new_lines)
        print(output)
        # update task comment with jupyter notebook server links
        if prev_line_count == 0:
            task.comment += '\n' + ''.join(line for line in new_lines if 'http://' in line or 'https://' in line)
        prev_line_count += len(new_lines)

    os.lseek(fd, 0, 0)
    os.ftruncate(fd, 0)

# cleanup
os.close(fd)
try:
    os.unlink(local_filename)
except:
    pass