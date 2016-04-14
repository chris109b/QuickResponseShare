#!/usr/bin/env python
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

from gi.repository import GObject as gobj, Gtk, GdkPixbuf, Gio

import tornado.ioloop
import tornado.web
import tornado.websocket

import urllib
import mimetypes
import re

from threading import Thread

import avahi
import dbus

import qrcode
import StringIO
import socket
import fcntl
import struct
import array
import getpass
import cairo
import rsvg


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
    number_of_bytes = max_possible * 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    names = array.array('B', '\0' * number_of_bytes)
    out_bytes = struct.unpack('iL', fcntl.ioctl(
        s.fileno(),
        0x8912,  # SIOCGIFCONF
        struct.pack('iL', number_of_bytes, names.buffer_info()[0])
    ))[0]
    name_string = names.tostring()
    lst = []
    for i in range(0, out_bytes, 40):
        name = name_string[i:i+16].split('\0', 1)[0]
        ip = name_string[i+20:i+24]
        lst.append((name, ip))
    return lst


def format_ip(address):
    return str(ord(address[0])) + '.' + \
           str(ord(address[1])) + '.' + \
           str(ord(address[2])) + '.' + \
           str(ord(address[3]))


def image_to_pixel_buffer(img):
    if img.mode != 'RGB':
        img = img.convert('RGB')
    buff = StringIO.StringIO()
    img.save(buff, 'ppm')
    contents = buff.getvalue()
    buff.close()
    loader = GdkPixbuf.PixbufLoader.new_with_type('pnm')
    loader.write(contents)
    pixel_buffer = loader.get_pixbuf()
    loader.close()
    return pixel_buffer


def get_icon_path(path, size=48):
    url = urllib.pathname2url(path)
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

    def __init__(self, name, port, service_type="_http._tcp", domain="", host="", text=""):
        self.name = name
        self.service_type = service_type
        self.domain = domain
        self.host = host
        self.port = port
        self.text = text
        self.group = None

    def publish(self):
        bus = dbus.SystemBus()
        server = dbus.Interface(bus.get_object(avahi.DBUS_NAME, avahi.DBUS_PATH_SERVER), avahi.DBUS_INTERFACE_SERVER)
        self.group = dbus.Interface(bus.get_object(avahi.DBUS_NAME, server.EntryGroupNew()), avahi.DBUS_INTERFACE_ENTRY_GROUP)
        self.group.AddService(avahi.IF_UNSPEC,
                              avahi.PROTO_UNSPEC,
                              dbus.UInt32(0),
                              self.name,
                              self.service_type,
                              self.domain,
                              self.host,
                              dbus.UInt16(self.port),
                              self.text)
        self.group.Commit()

    def unpublish(self):
        self.group.Reset()


# -------- Web server


class WebServer:
    
    def __init__(self, ip4address, port, ssl_cert_path):
        self.__ip4address = ip4address
        self.__port = port
        self.__ssl_cert_path = ssl_cert_path
        self.__zeroconf_service = None
        self.__application_service = None
        self.__clients = dict()
        self.__vendor_name = 'Christian Beuschel'
        self.__product_name = 'Quick Response Share'
        self.__version_string = '0.2'
        
    def get_text_record(self):
        node_info = {'vendor': self.__vendor_name,
                     'product': self.__product_name,
                     'version': self.__version_string}
        text = []
        for key, value in node_info.items():
            text.append(key + "=" + value)
        return avahi.string_array_to_txt_array(text)
                                              
    def start(self):
        # Publishing services
        self.__zeroconf_service = ZeroconfService(self.__product_name,
                                                  self.__port,
                                                  text=self.get_text_record())
        self.__zeroconf_service.publish()
        # Executing server
        self.__application_service = tornado.web.Application([(r'.*', DefaultHandler)])  
        self.__application_service.listen(self.__port)
        tornado.ioloop.IOLoop.instance().start()
        
    def stop(self):
        tornado.ioloop.IOLoop.current().stop()
        self.__zeroconf_service.unpublish()


class BasicRequestHandler(tornado.web.RequestHandler):

    def log(self, message):
        print message

    def send_file_not_found_error(self):
        self.log('Error: 404 File Not Found: %s' % self.request.path)
        raise tornado.web.HTTPError(404)
        
    def send_file_at_path(self, file_path, mime_type=None):
        try:
            if mime_type is None:
                url = urllib.pathname2url(file_path)
                mime_type, encoding = mimetypes.guess_type(url)
            if mime_type is None:
                mime_type = "application/octet-stream"
            f = open(file_path)
            self.set_header("Content-Type", mime_type)
            self.write(f.read())
            f.close()
            self.finish()
        except IOError:
            self.send_file_not_found_error()


class DefaultHandler(BasicRequestHandler):

    @tornado.web.asynchronous
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
        elif icon_pattern.match(path):
            try:
                head, index_string = os.path.split(path)
                index = int(index_string)
                file_path = file_list.get_icon_path_for_index(index)
                url = urllib.pathname2url(file_path)
                mime_type, encoding = mimetypes.guess_type(url)
                if mime_type == "image/svg+xml" or mime_type == "image/svg":
                    data = svg_to_png(file_path)
                    mime_type = "image/png"
                else:
                    f = open(file_path)
                    data = f.read()
                    f.close()
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
                url = urllib.pathname2url(file_path)
                mime_type, encoding = mimetypes.guess_type(url)
                if mime_type is None:
                    mime_type = "application/octet-stream"
                f = open(file_path)
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


# -------- Application


class Application(object):

    def __init__(self):
        # Network interfaces
        self.network_interfaces = get_all_network_interfaces()
        self.current_network_interface_index = -1
        eth_pattern = re.compile("^eth([0-9]+)$")
        wifi_pattern = re.compile("^wlan([0-9]+)$")
        index = 0
        for network_interface in self.network_interfaces:
            if eth_pattern.match(network_interface[0]):
                self.current_network_interface_index = index
                break
            elif wifi_pattern.match(network_interface[0]):
                self.current_network_interface_index = index
                break
            index += 1
        if self.current_network_interface_index == -1:
            self.current_network_interface_index = 0
        # Web server
        self.web_server_thread = None
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
        pixel_buffer = image_to_pixel_buffer(qr_image)
        self.image = Gtk.Image()
        self.image.set_from_pixbuf(pixel_buffer)
        vbox.pack_start(child=self.image, expand=False, fill=True, padding=0)
        # URI label
        self.label = Gtk.Label()
        self.label.set_markup("<a href=\"{0}\">{1}</a>".format(uri, uri))
        vbox.add(self.label)
        # Network interface switching button
        self.button = Gtk.Button(if_name)
        self.button.connect("clicked", self.switch_network_interface)
        vbox.add(self.button)
        # Show all
        self.window.show_all()

    def switch_network_interface(self, widget):
        self.current_network_interface_index = (self.current_network_interface_index + 1) % len(self.network_interfaces)
        self.stop_server()
        if_name, uri = self.start_server()
        self.button.set_label(if_name)
        self.label.set_markup("<a href=\"{0}\">{1}</a>".format(uri, uri))
        qr_image = get_qrcode(uri)
        pixel_buffer = image_to_pixel_buffer(qr_image)
        self.image.set_from_pixbuf(pixel_buffer)

    def stop_server(self):
        self.server.stop()
        self.web_server_thread.join()
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
        self.web_server_thread.start()

        return current_network_interface_name, current_uri

    def quit(self, arg1, arg2):
        self.stop_server()
        Gtk.main_quit(arg1, arg2)


# -------- Main


def main():
    for file_path in sys.argv[1:]:
        file_list.add(file_path)
    Application()
    gobj.threads_init()
    Gtk.main()

if __name__ == "__main__":
    file_list = FileList()
    main()