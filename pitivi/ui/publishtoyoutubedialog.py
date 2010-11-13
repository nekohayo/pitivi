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

class PublishToYouTubeDialog(GladeWindow, Renderer):
    glade_file = 'publishtoyoutubedialog.glade'

    def __init__(self, app, project, pipeline=None):
        Loggable.__init__(self)
        GladeWindow.__init__(self)

        self.app = app

        # UI widgets
        self.login = self.widgets["login"]

        Renderer.__init__(self, project, pipeline)

        self.window.connect("delete-event", self._deleteEventCb)

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
