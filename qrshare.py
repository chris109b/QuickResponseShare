#!/usr/bin/env python3
#
# qrshare - Quick Response Share Nautilus Integration
#
# This file is part of the Quick Response Share project.
# The program is designed for sharing files ad hoc to mobile clients
# via HTTP. It shows a QR code within a GTK window, that contains
# the URI of the integrated HTTP server.
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

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GObject as gobj, Gtk, GdkPixbuf, Gio
from gi.repository import GLib

import tornado.ioloop
import tornado.web
import tornado.websocket

import urllib.request
import mimetypes
import re

from threading import Thread

import zeroconf

import qrcode
import PIL.ImageOps

import socket
import fcntl
import struct
import array
import getpass

import base64

import cairosvg

import asyncio

from time import sleep

# -------- Functions

def format_file_size(file_size):
    file_size = float(file_size)
    size_names = ["kB", "MB", "GB"]
    size_name = "bytes"
    for name in size_names:
        if file_size > 1024:
            file_size /= 1024
            size_name = name
        else:
            break
    return "{0:3.2f} {1}".format(file_size, size_name)


def svg_to_png(svg_file_path):
    return cairosvg.svg2png(url=svg_file_path)

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
    img = qr.make_image(fill_color="black", back_color="white")
    return img


def get_all_network_interfaces():
    max_possible = 128  # arbitrary. raise if needed.
    number_of_bytes = max_possible * 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    names = array.array('B', b'\x00' * number_of_bytes)
    out_bytes = struct.unpack('iL', fcntl.ioctl(
        s.fileno(),
        0x8912,  # SIOCGIFCONF
        struct.pack('iL', number_of_bytes, names.buffer_info()[0])
    ))[0]
    name_string = names.tobytes()
    lst = []
    for i in range(0, out_bytes, 40):
        name = name_string[i:i+16].split(b'\x00', 1)[0]
        ip = name_string[i+20:i+24]
        lst.append((name, ip))
    return lst


def format_ip(address):
    return '{0}.{1}.{2}.{3}'.format(address[0], address[1], address[2], address[3])


def image_to_pixel_buffer(image):
    if image.mode != 'RGB':
        image = image.convert('RGB')
    pixels = image.load()
    if pixels[1,1] == (0, 0, 0):
        image = PIL.ImageOps.invert(image)
    arr = GLib.Bytes.new(image.tobytes())
    width, height = image.size
    pixel_buffer = GdkPixbuf.Pixbuf.new_from_bytes(arr, GdkPixbuf.Colorspace.RGB, False, 8, width, height, width * 3)
    return pixel_buffer


def get_icon_path(path, size=48):
    url = urllib.request.pathname2url(path)
    mime_type, encoding = mimetypes.guess_type(url)
    if mime_type is None:
        mime_type = "text/plain"
    iconname = Gio.content_type_get_icon(mime_type)
    theme = Gtk.IconTheme.get_default()
    icon = theme.choose_icon(iconname.get_names(), size, 0)
    if icon is None:
        iconname = Gio.content_type_get_icon("text/plain")
        icon = theme.choose_icon(iconname.get_names(), size, 0)
        return icon.get_filename()
    else:
        return icon.get_filename()


# -------- Zero conf service


class ZeroconfService:

    def __init__(self, ip_address, port, service_type="_http._tcp.local.", name="", hostname="", text=""):
        self.ip_address = ip_address
        self.port = port
        self.service_type = service_type
        self.name = name
        self.hostname = hostname
        self.text = text
        self.zeroconf = None
        self.info = None

    def publish(self):
        self.info = zeroconf.ServiceInfo(self.service_type,
                                        '{0}.{1}'.format(self.name, self.service_type),
                                         self.ip_address.encode(), self.port, 0, 0,
                                         self.text, '{0}.local.'.format(self.hostname))
        self.zeroconf = zeroconf.Zeroconf()
        self.zeroconf.register_service(self.info)

    def unpublish(self):
        self.zeroconf.unregister_service(self.info)
        self.zeroconf.close()


# -------- Web server


class WebServer:
    
    def __init__(self, ip4address, port, ssl_cert_path):
        self.__hostname = socket.gethostname()
        self.__ip4address = ip4address
        self.__port = port
        self.__ssl_cert_path = ssl_cert_path
        self.__zeroconf_service = None
        self.__application_service = None
        self.__server = None
        self.__clients = dict()
        self.__vendor_name = 'Christian Beuschel'
        self.__product_name = 'Quick Response Share'
        self.__version_string = '0.3'
        self.__net_app_version = '1'
        
    def get_text_record(self):
        node_info = {'net_app_version' : self.__net_app_version,
                     'vendor': self.__vendor_name,
                     'product': self.__product_name,
                     'version': self.__version_string}
        return node_info
                                              
    def start(self):
        # Publishing services
        self.__zeroconf_service = ZeroconfService(self.__ip4address,
                                                  self.__port,
                                                  service_type="_http._tcp.local.",
                                                  name=self.__product_name,
                                                  hostname=self.__hostname,
                                                  text=self.get_text_record())
        self.__zeroconf_service.publish()
        # Executing server
        asyncio.set_event_loop(asyncio.new_event_loop())
        self.__application_service = tornado.web.Application([(r'.*', DefaultHandler)])  
        self.__server = tornado.httpserver.HTTPServer(self.__application_service)
        self.loop = tornado.ioloop.IOLoop.instance()
        self.__server.listen(self.__port)
        self.loop.start()
        
    def stop(self):
        self.__zeroconf_service.unpublish()
        self.__server.stop()
        self.loop.stop()


class BasicRequestHandler(tornado.web.RequestHandler):

    def log(self, message):
        print(message)

    def send_file_not_found_error(self):
        self.log('Error: 404 File Not Found: %s' % self.request.path)
        raise tornado.web.HTTPError(404)
        
    def send_file_at_path(self, file_path, mime_type=None):
        try:
            if mime_type is None:
                url = urllib.request.pathname2url(file_path)
                mime_type, encoding = mimetypes.guess_type(url)
            if mime_type is None:
                mime_type = "application/octet-stream"
            with open(file_path, mode='rb') as f:
                self.set_header("Content-Type", mime_type)
                self.write(f.read())
            self.finish()
        except IOError:
            self.send_file_not_found_error()


class DefaultHandler(BasicRequestHandler):

    @tornado.gen.coroutine
    def get(self):
        path = self.request.path
        icon_pattern = re.compile("^\/%s\/([0-9]+)$" % file_list.get_icon_dir())
        file_pattern = re.compile("^\/%s\/([0-9]+)$" % file_list.get_file_dir())
        # Delivering content
        if (path == "/") or (path == "/index.html"):
            data = file_list.get_html
            self.set_header('Content-Type', 'text/html')
            self.set_header('Content-Length', '{0}'.format(len(data)))
            self.write(data)
            self.finish()
        elif (path == "/favicon.ico"):
            favicon = base64.b64decode( "AAABAAEAICAQAAEABADoAgAAFgAAACgAAAAgAAAAQAAAAAEABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAFRcVACUoJgA9Pz0ATlFPAGZpZwBydXMAe358AJGUkgClqKYAtbi1AMjMyQDW2dcA5OjlAPz//QAAAAAA7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7d3d3N7O3d3u3d7t7u7u7rFEREN+DZNH3mOe4N7u7u627u7sfg2a7QALt+AN7u7utuMzu37nvsbu7rfuTO7u7rbgAKxubKed7py37k3u7u624ACrfr7YjplL3Om+7u7utumZzH7u62oJSbzgve7u7rXd3dp+3dtnfpRIwG3u7u6xERERfgEZ7u7pnRHu7u7u7u7u7u4N647u6p7u7u7u7sVV2rxVDarFZVM1fn3u7u6wANlZzAzqnMC4jMgt7u7u2gDchqoJzbqb7LqbPe7u7toA3amZmd7Znsupnkzu7u6wB8m+3e3d7u1Qnt2N7u7usA5s6wDnCu7gAJ0A7u7u7u7u7u7uAAAF7u7u7u7u7u7Hd3d2ngyJted2d3d97u7utMvLyX4N2oXhrMvLPe7u7rbqutt+De2F4dyqvk3u7u624ACsfpvduuHZAD5N7u7utuAAq37VvJ3hyQA+TO7u7rbgAKx+AL7F4dkAPk3u7u627u7rfgC7juHe7u5N7u7us2d3dX7WuzjhV3d3LO7u7tu7u7vO7N2867u7u77u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==")
            self.set_header('Content-Type', 'image/x-icon')
            self.set_header('Content-Length', '{0}'.format(len(favicon)))
            self.write(favicon)
            
        elif icon_pattern.match(path):
            try:
                head, index_string = os.path.split(path)
                index = int(index_string)
                file_path = file_list.get_icon_path_for_index(index)
                url = urllib.request.pathname2url(file_path)
                mime_type, encoding = mimetypes.guess_type(url)
                if mime_type == "image/svg+xml" or mime_type == "image/svg":
                    data = svg_to_png(file_path)
                    mime_type = "image/png"
                else:
                    data = ''
                    with open(file_path, mode='rb') as f:
                        data = f.read()
                if mime_type is not None:
                    self.set_header('Content-Type', mime_type)
                self.set_header('Content-Length', '{0}'.format(len(data)))
                self.write(data)
                self.finish()
            except IOError:
                self.send_file_not_found_error()
        elif file_pattern.match(path):
            try:
                head, index_string = os.path.split(path)
                index = int(index_string)
                file_path = file_list.get_file_path_for_index(index)
                head, filename = os.path.split(file_path)
                url = urllib.request.pathname2url(file_path)
                mime_type, encoding = mimetypes.guess_type(url)
                if mime_type is None:
                    mime_type = "application/octet-stream"
                data = ''
                with open(file_path, mode='rb') as f:
                    data = f.read()
                self.set_header('Content-Type', mime_type)
                self.set_header('Content-Length', '{0}'.format(len(data)))
                self.set_header('Content-Disposition', 'attachment;filename="{0}";'.format(filename))
                self.write(data)
                self.finish()
                f.close()
            except IOError:
                self.send_file_not_found_error()
        else:
            self.send_file_not_found_error()


# --------- File list / data model


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
        div.footer
        {
            font-size:80%;
            font-weight:normal;
            padding:12px 0px 12px 0px;
            width:100%;
            margin:0px;
            background-color:#2C001E;
            color:white;
            display:block;
            position:fixed;
            bottom:0px;
            left:0px;
            text-align:center;
            line-height:100%;
        }
        h1,
        div.footer {
            box-shadow: 0px 1px 8px rgba(0, 0, 0, 0.8);
        }
        a.footer,
        a.file:link,
        a.file:visited
        {
            color:white;
            text-decoration:none;
        }
        a.file:active,
        a.file:hover
        {
            text-decoration:underline;
        }
        div.table
        {
            width:100%;
            margin-top:57px;
            margin-bottom:57px;
            border-top:1px solid #2C001E;
        }
        a.file
        {
            display:block;
            width:97%;
            padding:15px 0px 11px 1%;
            margin:0px 1% 0px 1%;
            border-bottom:1px solid #2C001E;
            text-decoration:none;
            color:black;
        }
        a.file:link
        {
            color:black;
        }
        a.file:visited
        {
            color:#DD4814;
        }
        a.file:active,
        a.file:hover
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
            html += "<a class=\"file\" href=\"%s\"><img src=\"%s\">%s &nbsp;&nbsp;&nbsp;<span>(%s)</span></a>" % \
                    (link, img_src, filename, formatted_size)
            index += 1
        html += "</div>"
        html += "<h1>QRshare - %s@%s</h1>" % (self.username, self.hostname)
        html += "<div class=\"footer\"><a class=\"footer\" href=\"https://github.com/chris109b/QuickResponseShare\">Qick Response Share is distributed under the General Public License.</div>"
        html += "</body>\n</html>"
        return html


# -------- Application


class Application(object):

    def __init__(self):
        # Network interfaces
        self.network_interfaces = get_all_network_interfaces()
        self.current_network_interface_index = 0
        index = 0
        for network_interface_name, network_interface_ip in self.network_interfaces:
            network_interface_name = network_interface_name.decode("utf-8") 
            if network_interface_name != 'lo':
                self.current_network_interface_index = index
                break
            index += 1
        # Web server
        self.web_server_thread = None
        self.server = None
        if_name, uri = self.start_server()
        # Window
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_icon_from_file('/usr/share/pixmaps/qrshare.png')
        self.window.set_title("QRshare")
        self.window.set_default_size(300, 360)
        self.window.connect("destroy", self.quit, "WM destroy")
        # Layout
        vbox = Gtk.VBox()
        self.window.add(vbox)
        # QR code image
        self.image = Gtk.Image()
        vbox.pack_start(child=self.image, expand=False, fill=True, padding=0)
        # URI label
        self.label = Gtk.Label()
        vbox.add(self.label)
        # Network interface switching button
        self.button = Gtk.Button()
        self.button.connect("clicked", self.switch_network_interface)
        vbox.add(self.button)
        # Initial label update
        self.update_labels(if_name, uri)
        # Show all
        self.window.show_all()

    def update_labels(self, if_name, uri):
        self.button.set_label("Netwoork interface: {0}".format(if_name.decode("utf-8")))
        self.label.set_markup("<a href=\"{0}\">{1}</a>".format(uri, uri))
        qr_image = get_qrcode(uri)
        pixel_buffer = image_to_pixel_buffer(qr_image)
        self.image.set_from_pixbuf(pixel_buffer)

    def switch_network_interface(self, widget):
        self.current_network_interface_index = (self.current_network_interface_index + 1) % len(self.network_interfaces)
        self.stop_server()
        if_name, uri = self.start_server()
        self.update_labels(if_name, uri)

    def stop_server(self):
        self.server.stop()
        self.server = None

    def start_server(self):
        current_network_interface = self.network_interfaces[self.current_network_interface_index]
        current_network_interface_name = current_network_interface[0]
        current_ip = format_ip(current_network_interface[1])
        current_port = get_free_port()
        current_uri = "http://%s:%s/" % (current_ip, current_port)
        file_list.set_base_uri(current_uri)

        self.server = WebServer(current_ip, current_port, None)
        self.web_server_thread = Thread(target=self.server.start)
        self.web_server_thread.daemon = True
        self.web_server_thread.start()

        return current_network_interface_name, current_uri

    def quit(self, arg1, arg2):
        self.window.hide()
        self.stop_thread = Thread(target=self.stop_server)
        self.stop_thread.daemon = True
        self.stop_thread.start()
        Gtk.main_quit(arg1, arg2)

# -------- Main


def main():
    for file_path in sys.argv[1:]:
        file_list.add(file_path)
    app = Application()
    Gtk.main()
    sleep(3)


if __name__ == "__main__":
    file_list = FileList()
    main()
