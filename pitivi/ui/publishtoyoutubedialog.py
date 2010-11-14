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

import tempfile, os, gtk
from pitivi.log.loggable import Loggable
from pitivi.ui.glade import GladeWindow
from pitivi.actioner import Renderer
from pitivi.ui.exportsettingswidget import ExportSettingsDialog
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

        self.progressbar = self.widgets["progressbar"]

        # Assistant pages
        self.login_page = self.window.get_nth_page(0)
        self.metadata_page = self.window.get_nth_page(1)
        self.render_page = self.window.get_nth_page(2)
        self.announce_page = self.window.get_nth_page(3)

        self.description.get_buffer().connect("changed", self._descriptionChangedCb)

        self.window.connect("delete-event", self._deleteEventCb)

        self.tmpdir = tempfile.mkdtemp()
        self.fifoname = os.path.join(self.tmpdir, 'pitivi_rendering_fifo')
        os.mkfifo(self.fifoname)

        # TODO: This is probably not the best way to build an URL
        #self.outfile = 'file:/home/mag/test.webm' #'file:' + self.fifoname
        outfile = 'file://' + self.fifoname

        Renderer.__init__(self, project, pipeline, outfile = outfile)

        # YouTube integration
        self.yt = AsyncYT()
        self.metadata = {
            "title": "",
            "description": "",
            "private": True,
        }
        self.has_started_rendering = False

    def _shutDown(self):
        self.debug("shutting down")
        self.yt.stop()

        try:
            os.remove(self.fifoname)
        except OSError:
            pass

        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

        # Abort recording
        self.removeAction()
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
        # TODO: Use self.yt.authenticate_with_token if we have a login token

    def _loginResultCb(self, result):
        # TODO: The throbber should now be deactivated
        status = result[0]
        if status == 'good':
            status, login_token = result
            # TODO: The login token should be stored and reused
            # rather than forcing login with password every time
            self.login_status.set_text("Logged in")
            self.window.set_page_complete(self.login_page, True)
        else:
            status, exception = result
            self.login_status.set_text(str(exception))
            self.window.set_page_complete(self.login_page, False)

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

    def _prepareCb(self, assistant, page):
        if page == self.render_page and not self.has_started_rendering:
            self._startRenderAndUpload()

    def _stupidlyGetSettingsFromUser(self):
        dialog = ExportSettingsDialog(self.app, self.settings)
        res = dialog.run()
        dialog.hide()
        if res == gtk.RESPONSE_ACCEPT:
            self.settings = dialog.getSettings()
        dialog.destroy()

    def _startRenderAndUpload(self):
        # TODO: These settings should:
        #  * Have a page in the assistant
        #  * Be incredibly narrowed down for the YouTube use case:
        #     * WebM (vp8/vorbis) is always appropriate
        #     * We could offer for example three quality categories
        #
        # In the mean time, pop up the entire settings-dialog:
        self._stupidlyGetSettingsFromUser()

        self.has_started_rendering = True
        
        # Start uploading:
        self.yt.upload(lambda: PipeWrapper(open(self.fifoname, 'rb')), self.metadata, self._uploadDoneCb)

        # Start rendering:
        self.startAction()

    def updatePosition(self, fraction, text):
        self.progressbar.set_fraction(fraction)
        if text is not None:
            self.progressbar.set_text(_("About %s left") % text)

    def _uploadDoneCb(self, result):
        if result[0] == "good":
            status, new_entry = result
            self.window.set_page_complete(self.render_page, True)
        else:
            status, exception = result
            # TODO: Something about the error status
