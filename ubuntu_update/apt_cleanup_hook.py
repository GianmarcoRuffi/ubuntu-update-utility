#!/usr/bin/python3 -I
"""Ask the worker to approve APT's actual removal transaction."""
import json
import os
import re
import socket
import sys


def removals(stream):
    if stream.readline().strip() != 'VERSION 3':
        raise ValueError('Protocollo APT non supportato')
    for line in stream:
        if not line.strip():
            break
    else:
        raise ValueError('Intestazione APT incompleta')
    packages = set()
    for line in stream:
        fields = line.split()
        if (len(fields) != 9 or fields[4:7] != ['>', '-', '-']
                or fields[7] not in ('none', 'no') or fields[8] != '**REMOVE**'):
            raise ValueError('Operazione APT inattesa')
        name, version, arch = fields[:3]
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', name) or not re.fullmatch(r'[a-z0-9-]+', arch):
            raise ValueError('Pacchetto APT non identificabile')
        packages.add((name, arch, version))
    return sorted(packages)


def main():
    if os.geteuid() != 0:
        return 1
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(os.environ['UPDATE_UTILITY_APT_SOCKET'])
        try:
            message = {'packages': removals(sys.stdin)}
        except ValueError as error:
            message = {'error': str(error)}
        connection.sendall(json.dumps(message).encode() + b'\n')
        return int(connection.recv(1) != b'Y')


if __name__ == '__main__':
    sys.exit(main())
