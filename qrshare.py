#!/usr/bin/env python
#
# qrshare - Quick Response Share Nautilus Integration
#
# This file is part of the Quick Response Share project.
# The program is designed for sharing files ad hoc to mobile clients
# via HTTP. It shows a QR code within a GTK window, that contains
# the URI of the integraget HTTP server.
#
# This file contains the core application.
#
# Copyright (C) 2015 Christian Beuschel <chris109@web.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA

import os
import sys
from gi.repository import GObject, Gtk, GdkPixbuf, Gio
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn
from threading import Thread
import re
import urlparse
import mimetypes
import qrcode
import StringIO
import socket
import fcntl
import struct
import array
import getpass
import cairo
import rsvg


class Application(object):

    def __init__(self):
        # Network interfaces
        self.network_interfaces = get_all_network_interfaces()
        self.current_network_interface_index = -1
        eth_pattern = re.compile("^eth([0-9]+)$")
        wlan_pattern = re.compile("^wlan([0-9]+)$")
        index = 0
        for network_interface in self.network_interfaces:
            if eth_pattern.match(network_interface[0]):
                self.current_network_interface_index = index
                break
            elif wlan_pattern.match(network_interface[0]):
                self.current_network_interface_index = index
                break
            index += 1
        if self.current_network_interface_index == -1:
            self.current_network_interface_index = 0
        # Web server
        self.server = None
        if_name, uri = self.start_server()
        qr_image = get_qrcode(uri)
        # Window
        self.window = Gtk.Window(Gtk.WindowType.TOPLEVEL)
        self.window.set_title("QRshare")
        self.window.set_default_size(300, 360)
        self.window.connect("destroy", self.quit, "WM destroy")
        # Layout
        vbox = Gtk.VBox()
        self.window.add(vbox)
        # QR code image
        pixbuf = image2pixbuf(qr_image)
        self.image = Gtk.Image()
        self.image.set_from_pixbuf(pixbuf)
        vbox.pack_start(child=self.image, expand=False, fill=True, padding=0)
        # URI label
        self.label = Gtk.Label(uri)
        vbox.add(self.label)
        # Network interface switching button
        self.button = Gtk.Button(if_name)
        self.button.connect("clicked", self.switch_network_interface)
        vbox.add(self.button)
        # Show all
        self.window.show_all()

    def switch_network_interface(self, w):
        self.current_network_interface_index = (self.current_network_interface_index + 1) % len(self.network_interfaces)
        self.stop_server()
        if_name, uri = self.start_server()
        self.button.set_label(if_name)
        self.label.set_text(uri)
        qr_image = get_qrcode(uri)
        pixbuf = image2pixbuf(qr_image)
        self.image.set_from_pixbuf(pixbuf)

    def stop_server(self):
        self.server.socket.close()
        self.server = None

    def start_server(self):
        current_network_interface = self.network_interfaces[self.current_network_interface_index]
        current_network_interface_name = current_network_interface[0]
        current_ip = format_ip(current_network_interface[1])
        current_port = get_free_port()
        current_uri = "http://%s:%s/" % (current_ip, current_port)
        file_list.set_base_uri(current_uri)

        self.server = ThreadingHttpServer((current_ip, int(current_port)), HttpHandler)
        web_server_thread = Thread(target=self.server.serve_forever)
        web_server_thread.start()

        return current_network_interface_name, current_uri

    def quit(self, arg1, arg2):
        self.stop_server()
        Gtk.main_quit(arg1, arg2)


class FileList:

    def __init__(self):
        self.base_uri = ""
        self.file_dir = "files"
        self.icon_dir = "icons"
        self.path_list = list()
        self.icon_list = list()
        self.size_list = list()
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()

    def set_base_uri(self, uri):
        self.base_uri = uri

    def get_base_uri(self):
        return self.base_uri

    def get_file_dir(self):
        return self.file_dir

    def get_icon_dir(self):
        return self.icon_dir

    def add(self, path):
        if os.path.isfile(path):
            self.path_list.append(path)
            self.icon_list.append(get_icon_path(path))
            self.size_list.append(format_file_size(os.path.getsize(path)))

    def get_file_path_for_index(self, index):
        return self.path_list[index]

    def get_icon_path_for_index(self, index):
        return self.icon_list[index]

    @property
    def get_html(self):
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="content-type" content="text/html; charset=UTF-8">
    <meta http-equiv="content-style-type" content="text/css">
    <meta name="viewport" content="width = device-width, initial-scale = 1.0, user-scalable = no">
    <title>QRshare</title>
    <style>
        html, body
        {
            width:100%;
            padding:0px;
            margin:0px;
            background-color:#F1F1F1;
        }
        body {
            font-family:Ubuntu, sans-serif;
            font-size:18px;
            line-height:150%;
        }
        h1
        {
            font-size:140%;
            font-weight:normal;
            padding:15px 0px 15px 2%;
            width:98%;
            height:28px;
            margin:0px;
            background-color:#2C001E;
            color:white;
            display:block;
            position:fixed;
            top:0px;
            left:0px;
        }
        div.table
        {
            width:100%;
            margin-top:57px;
            border-top:1px solid #2C001E;
        }
        a
        {
            display:block;
            width:97%;
            padding:15px 0px 11px 1%;
            margin:0px 1% 0px 1%;
            border-bottom:1px solid #2C001E;
            text-decoration:none;
            color:black;
        }
        a:link
        {
            color:black;
        }
        a:visited
        {
            color:#DD4814;
        }
        a:active,
        a:hover
        {
            color:#DD4814;
            text-decoration:underline;
        }
        img
        {
            width:24px;
            height:24px;
            vertical-align: middle;
            margin-bottom:4px;
            margin-right:4px;
        }
        span
        {
            font-size:80%;
        }
    </style>
</head>
<body>
<div class="table">"""
        index = 0
        for path in self.path_list:
            link = self.base_uri + self.file_dir + "/" + str(index)
            img_src = self.base_uri + self.icon_dir + "/" + str(index)
            formatted_size = self.size_list[index]
            head, filename = os.path.split(path)
            html += "<a href=\"%s\"><img src=\"%s\">%s &nbsp;&nbsp;&nbsp;<span>(%s)</span></a>" % \
                    (link, img_src, filename, formatted_size)
            index += 1
        html += "</div>"
        html += "<h1>QRshare - %s@%s</h1>" % (self.username, self.hostname)
        html += "</body>\n</html>"
        return html


class ThreadingHttpServer(ThreadingMixIn, HTTPServer):
    pass


class HttpHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        # Reading variables from GET request
        scheme, netloc, path, params, query, fragment = urlparse.urlparse(self.path)
        print path
        icon_pattern = re.compile("^\/%s\/([0-9]+)$" % file_list.get_icon_dir())
        file_pattern = re.compile("^\/%s\/([0-9]+)$" % file_list.get_file_dir())
        # Delivering content
        if (path == "/") or (path == "/index.html"):
            data = file_list.get_html
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', '{0}'.format(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif icon_pattern.match(path):
            print "Icon"
            try:
                head, index_string = os.path.split(path)
                index = int(index_string)
                file_path = file_list.get_icon_path_for_index(index)
                mimetype, othervalue = mimetypes.guess_type(file_path)
                print mimetype
                if mimetype == "image/svg+xml" or mimetype == "image/svg":
                    data = svg_to_png(file_path)
                    mimetype = "image/png"
                else:
                    f = open(file_path)
                    data = f.read()
                    f.close()
                print mimetype
                self.send_response(200)
                self.send_header('Content-Type', mimetype)
                self.send_header('Content-Length', '{0}'.format(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except IOError:
                self.send_error(404, 'File Not Found: %s' % self.path)
        elif file_pattern.match(path):
            try:
                head, index_string = os.path.split(path)
                index = int(index_string)
                file_path = file_list.get_file_path_for_index(index)
                head, filename = os.path.split(file_path)
                mimetype = mimetypes.guess_type(file_path)
                f = open(file_path)
                data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', mimetype)
                self.send_header('Content-Length', '{0}'.format(len(data)))
                self.send_header('Content-Disposition', 'attachment;filename="{0}";'.format(filename))
                self.end_headers()
                self.wfile.write(data)
                f.close()
            except IOError:
                self.send_error(404, 'File Not Found: %s' % self.path)
        else:
            self.send_error(404, 'File Not Found: %s' % self.path)


def format_file_size(filesize):
    filesize = float(filesize)
    sizenames = ["kB", "MB", "GB"]
    sizename = "bytes"
    for name in sizenames:
        if filesize > 1024:
            filesize /= 1024
            sizename = name
        else:
            break
    return "{0:3.2f} {1}".format(filesize, sizename)


def svg_to_png(svg_file_path):
    print svg_file_path
    img = cairo.ImageSurface(cairo.FORMAT_ARGB32, 48, 48)
    ctx = cairo.Context(img)
    handle = rsvg.Handle(svg_file_path)
    handle.render_cairo(ctx)
    png_buffer = StringIO.StringIO()
    img.write_to_png(png_buffer)
    png_buffer.seek(0)
    return png_buffer.read()

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def get_qrcode(data_string):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4)
    qr.add_data(data_string)
    qr.make(fit=True)
    img = qr.make_image()
    return img


def get_all_network_interfaces():
    max_possible = 128  # arbitrary. raise if needed.
    numberofbytes = max_possible * 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    names = array.array('B', '\0' * numberofbytes)
    outbytes = struct.unpack('iL', fcntl.ioctl(
        s.fileno(),
        0x8912,  # SIOCGIFCONF
        struct.pack('iL', numberofbytes, names.buffer_info()[0])
    ))[0]
    namestr = names.tostring()
    lst = []
    for i in range(0, outbytes, 40):
        name = namestr[i:i+16].split('\0', 1)[0]
        ip = namestr[i+20:i+24]
        lst.append((name, ip))
    return lst


def format_ip(addr):
    return str(ord(addr[0])) + '.' + \
           str(ord(addr[1])) + '.' + \
           str(ord(addr[2])) + '.' + \
           str(ord(addr[3]))


def image2pixbuf(img):
    if img.mode != 'RGB':
        img = img.convert('RGB')
    buff = StringIO.StringIO()
    img.save(buff, 'ppm')
    contents = buff.getvalue()
    buff.close()
    loader = GdkPixbuf.PixbufLoader.new_with_type('pnm')
    loader.write(contents)
    pixbuf = loader.get_pixbuf()
    loader.close()
    return pixbuf


def get_icon_path(path, size=48):
    mimetype, encoding = mimetypes.guess_type(path)
    if mimetype:
        iconname = Gio.content_type_get_icon(mimetype)
        theme = Gtk.IconTheme.get_default()
        icon = theme.choose_icon(iconname.get_names(), size, 0)
        if icon is None:
            iconname = Gio.content_type_get_icon("text/plain")
            icon = theme.choose_icon(iconname.get_names(), size, 0)
            return icon.get_filename()
        else:
            return icon.get_filename()



if __name__ == "__main__":
    file_list = FileList()
    for filepath in sys.argv[1:]:
        file_list.add(filepath)
    Application()
    GObject.threads_init()
    Gtk.main()
