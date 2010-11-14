# PiTiVi , Non-linear video editor
#
#       ui/publishtoyoutubedialog.py
#
# Copyright (c) 2010, Magnus Hoff <maghoff@gmail.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

"""
Dialog for publishing to YouTube
"""

from pitivi.log.loggable import Loggable
from pitivi.ui.glade import GladeWindow
from pitivi.actioner import Renderer
from pitivi.youtube_glib import AsyncYT, PipeWrapper

class PublishToYouTubeDialog(GladeWindow, Renderer):
    glade_file = 'publishtoyoutubedialog.glade'

    def __init__(self, app, project, pipeline=None):
        Loggable.__init__(self)
        GladeWindow.__init__(self)

        self.app = app

        # UI widgets
        self.login = self.widgets["login"]
        self.login_status = self.widgets["login_status"]
        self.username = self.widgets["username"]
        self.password = self.widgets["password"]
        
        self.description = self.widgets["description"]
        
        # Assistant pages
        self.login_page = self.window.get_nth_page(0)
        self.metadata_page = self.window.get_nth_page(1)
        self.render_page = self.window.get_nth_page(2)
        self.announce_page = self.window.get_nth_page(3)

        self.description.get_buffer().connect("changed", self._descriptionChangedCb)

        Renderer.__init__(self, project, pipeline)

        self.window.connect("delete-event", self._deleteEventCb)

        # YouTube integration
        self.yt = AsyncYT()
        self.metadata = {
            "title": "",
            "description": "",
            "private": True,
        }

    def destroy(self):
        self.yt.stop()
        GladeWindow.destroy(self)

    def _shutDown(self):
        self.debug("shutting down")
        # Abort recording
        #self.removeAction()
        self.destroy()

    def _deleteEventCb(self, window, event):
        self.debug("delete event")
        self._shutDown()

    def _cancelCb(self, ignored):
        self.debug("cancel event")
        self._shutDown()

    def _loginClickedCb(self, *args):
        self.debug("login clicked")
        self.login_status.set_text("Logging in...")
        # TODO: This should activate a throbber
        self.yt.authenticate_with_password(self.username.get_text(), self.password.get_text(), self._loginResultCb)

    def _loginResultCb(self, token):
        self.login_status.set_text("Logged in")
        # TODO: The throbber should now be deactivated
        self.window.set_page_complete(self.login_page, True)

    def _update_metadata_page_complete(self):
        is_complete = all([
            len(self.metadata["title"]) != 0,
            len(self.metadata["description"]) != 0,
        ])
        self.window.set_page_complete(self.metadata_page, is_complete)

    def _titleChangedCb(self, widget):
        self.metadata["title"] = widget.get_text()
        self._update_metadata_page_complete()

    def _descriptionChangedCb(self, buffer):
        self.metadata["description"] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter())
        self._update_metadata_page_complete()
