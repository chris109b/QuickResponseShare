#!/usr/bin/env python
#
# qrshare - Quick Response Share Nautilus Integration
#
# This file is part of the Quick Response Share project.
# The program is designed for sharing files ad hoc to mobile clients
# via HTTP. It shows a QR code within a GTK window, that contains
# the URI of the integrated HTTP server.
#
# This file integrates the sharing function to the file context
# menu of Nautilus File Manager.
#
# For personal installation copy this file to:
# ~/.local/share/nautilus-python/extensions/
#
# For system wide installation copy this file to:
# /usr/share/nautilus-python/extensions/
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


from gi.repository import Nautilus, GObject
import subprocess


class ColumnExtension(GObject.GObject, Nautilus.MenuProvider):

    def __init__(self):
        print "qrshare - Quick Response Share Nautilus Integration"

    def menu_activate_receive_files(self, menu, folder):
        call_list = list()
        call_list.append("qrreceive")
        location = folder.get_location()
        path = location.get_parse_name()
        call_list.append(path)
        subprocess.Popen(call_list)

    def menu_activate_share_files(self, menu, files):
        call_list = list()
        call_list.append("qrshare")
        for file_info in files:
            location = file_info.get_location()
            path = location.get_parse_name()
            call_list.append(path)
        subprocess.Popen(call_list)

    def get_file_items(self, window, files):
        usable_files = list()
        for file_info in files:
            if not file_info.is_directory():
                usable_files.append(file_info)

        if len(usable_files) == 0:
            return

        share_item = Nautilus.MenuItem(
            name="QuickShareExtension::Share",
            label="Quick share {0} files".format(len(usable_files)),
            tip="Share files to a smart phone, tablet or PC"
        )
        share_item.connect('activate', self.menu_activate_share_files, usable_files)

        return [share_item]

    def get_background_items(self, window, folder):
        receive_item = Nautilus.MenuItem(
            name="QuickShareExtension::Receive",
            label="Receive Smart Phone images",
            tip="Create an inbox folder to receive files from a smart phone, tablet or PC"
        )
        receive_item.connect('activate', self.menu_activate_cb, folder)
