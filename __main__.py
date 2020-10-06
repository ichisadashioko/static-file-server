#!/usr/bin/env python3
# encoding=utf-8
import os
import sys
import argparse
import http
import http.server
from functools import partial

from __init__ import StaticFileServer

parser = argparse.ArgumentParser()

parser.add_argument('port', action='store', nargs='?', default=8080, type=int)
parser.add_argument('--directory', '-d', default=os.getcwd())

args = parser.parse_args()
print(args)

if not os.path.exists(args.directory):
    raise Exception(args.directory, 'does not exist!')

if os.path.isfile(args.directory):
    raise Exception(args.directory, 'is a file!')

serve_directory = os.path.abspath(args.directory)

handler_class = partial(StaticFileServer, directory=serve_directory)

with http.server.ThreadingHTTPServer(('localhost', args.port), handler_class) as httpd:
    print(f'Serving \"{serve_directory}\" at http://localhost:{args.port}')

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nKeyboard interrupt received, exiting.')
        sys.exit(0)
