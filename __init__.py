#!/usr/bin/env python3
# encoding=utf-8
import os
import re
import time
import shutil
import posixpath
import mimetypes
import html
import io
import email.utils
import datetime
import json
from typing import List

import http
from http.server import BaseHTTPRequestHandler

import urllib
import urllib.parse


class StaticFileServer(BaseHTTPRequestHandler):

    def __init__(self, *args, directory=None, **kwargs):
        if directory is None:
            directory = os.getcwd()
        self.directory = directory
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str):
        words = path.split('/')
        words = filter(None, words)
        words = filter(lambda word: len(word) > 0, words)
        # decode every path components because there might be some
        # spaces or some hash characters in the file name but those
        # characters are not able to represent as they are in the url
        # components
        words = map(lambda word: urllib.parse.unquote(word), words)

        path = '/'
        local_path = self.directory

        for word in words:
            if os.path.dirname(word) or (word in (os.curdir, os.pardir)):
                # ignore components that are not simple file/directory name
                continue

            path = posixpath.join(path, word)
            local_path = os.path.join(local_path, word)

        return path, local_path

    def list_directory(self, displayname: str, local_path: str):
        try:
            file_list = os.listdir(local_path)
        except OSError:
            self.send_error(http.HTTPStatus.NOT_FOUND, 'No permission to list directory!')
            return None

        # TODO options to sort by name, creation date, or last modified date
        document = ['<pre>']

        for child_filename in file_list:
            child_filepath = os.path.join(local_path, child_filename)
            child_displayname = linkname = child_filename
            # append / for directories or @ for symbalic links
            if os.path.isdir(child_filepath):
                child_displayname = child_filename + '/'
                linkname = child_filename + '/'
            if os.path.islink(child_filepath):
                child_displayname = child_filename + '@'

            quoted_linkname = urllib.parse.quote(linkname, errors='surrogatepass')
            escaped_displayname = html.escape(child_displayname)
            document.append(f'<a href="{quoted_linkname}">{escaped_displayname}</a>')

        document.append('</pre>')
        document = '\n'.join(document)

        encoded_document = document.encode('utf-8', 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded_document)
        f.seek(0)
        self.send_response(http.HTTPStatus.OK)
        self.send_header('Content-Type', 'text/html; charset=UTF-8')
        self.send_header('Content-Length', str(len(encoded_document)))
        self.end_headers()
        return f

    def send_head(self):
        parts = urllib.parse.urlsplit(self.path)
        path, local_path = self.translate_path(parts.path)

        query_dict = urllib.parse.parse_qs(parts.query, keep_blank_values=True)

        f = None
        if os.path.isdir(local_path):
            if not parts.path.endswith('/'):
                self.send_response(http.HTTPStatus.MOVED_PERMANENTLY)
                new_parts = (parts[0], parts[1], parts[2] +
                             '/', parts[3], parts[4])
                new_url = urllib.parse.urlunsplit(new_parts)
                self.send_header('Location', new_url)
                self.end_headers()
                return None

            # if there is a query parameter named 'listdir' then force directory listing instead of seeking for index document
            if 'listdir' in query_dict:
                return self.list_directory(displayname=path, local_path=local_path)
            else:
                for index in ('index.html', 'index.htm'):
                    index = os.path.join(local_path, index)
                    if os.path.exists(index):
                        local_path = index
                        break
                else:
                    return self.list_directory(displayname=path, local_path=local_path)

        # if the execution reaches here then that means we have to send a file
        if not os.path.exists(local_path):
            self.send_error(http.HTTPStatus.NOT_FOUND, 'File not found!')
            return None

        # TODO check extension and send Content-Type in headers
        ctype = self.guess_type(local_path)

        f = open(local_path, 'rb')
        try:
            fs = os.fstat(f.fileno())
            # use browser cache if possible
            if ('If-Modified-Since' in self.headers) and ('If-None-Match' not in self.headers):
                # compare If-Modified-Since and time of the last file modification
                try:
                    ims = email.utils.parsedate_to_datetime(
                        self.headers['If-Modified-Since'])
                except (TypeError, IndexError, OverflowError, ValueError):
                    # ignore ill-formed values
                    pass
                else:
                    if ims.tzinfo is None:
                        # obsolete format with no timezone, cf
                        # https://tools.ietf.org/html/rfc7231#section-7.1.1.1
                        ims = ims.replace(tzinfo=datetime.timezone.utc)
                    if ims.tzinfo is datetime.timezone.utc:
                        # compare to UTC datetime of last modification
                        last_modif = datetime.datetime.fromtimestamp(
                            fs.st_mtime, datetime.timezone.utc)
                        # remove microseconds, like in If-Modified-Since
                        last_modif = last_modif.replace(microsecond=0)

                        if last_modif <= ims:
                            self.send_response(http.HTTPStatus.NOT_MODIFIED)
                            self.end_headers()
                            f.close()
                            return None

            self.send_response(http.HTTPStatus.OK)
            if ctype == 'text/plain':
                self.send_header('Content-Type', ctype+';charset=UTF-8')
            else:
                self.send_header('Content-Type', ctype)
            print(ctype)
            # TODO handle symbolic link
            self.send_header('Content-Length', str(fs.st_size))
            self.send_header(
                'Last-Modified', self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except:
            f.close()
            raise

    def date_time_string(self, timestamp=None):
        if timestamp is None:
            timestamp = time.time()

        return email.utils.formatdate(timestamp, usegmt=True)

    def guess_type(self, path: str):
        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]

        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    def do_GET(self):
        f = self.send_head()
        if f:
            try:
                shutil.copyfileobj(f, self.wfile)
            finally:
                f.close()

    def do_POST(self):
        """
        All the API will be accessed via POST method so that we can
        still keep the static file serving.
        """
        # TODO override all these do_XXX method for your application
        self.send_error(http.HTTPStatus.NOT_FOUND, 'API endpoint does not exist!')

    if not mimetypes.inited:
        mimetypes.init()  # try to read system mime.tyeps

    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream',  # default
        '.html': 'text/html',
        '.htm': 'text/html',
        '.css': 'text/css',
        # TODO flag to enable or disable ES module
        '.js': 'application/javascript',
        '.es': 'application/ecmascript',
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
        '.tsv': 'text/plain',
        '.txt': 'text/plain',
        '.cfg': 'text/plain',
        '.gitconfig': 'text/plain',
    })
