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
from projectsettings import ProjectSettingsDialog
from pitivi.youtube_glib import AsyncYT, PipeWrapper
from gettext import gettext as _
from gtk import ProgressBar
from gobject import timeout_add
from string import ascii_lowercase, ascii_uppercase, maketrans, translate
try :
    import gnomekeyring as gk
    unsecure_storing = False
except :
    unsecure_storing = True

catlist = ['Film', 'Autos', 'Music', 'Animals', 'Sports', 'Travel', 'Games', 'Comedy', 'People', 'News', 'Entertainment', 'Education', 'Howto', 'Nonprofit', 'Tech']

class PublishToYouTubeDialog(GladeWindow, Renderer):
    glade_file = 'publishtoyoutubedialog.glade'

    def __init__(self, app, project, pipeline=None):
        Loggable.__init__(self)
        GladeWindow.__init__(self)
        self.app_settings = app.settings

        self.app = app
        self.pipeline = pipeline

        # UI widgets
        self.login = self.widgets["login"]
        self.login_status = self.widgets["login_status"]
        self.username = self.widgets["username"]
        self.password = self.widgets["password"]
        self.oldsettings = self.app.project.getSettings()
        self.settings = self.oldsettings.copy()
        self.settings.setEncoders(muxer='avimux', vencoder='xvidenc', aencoder="lamemp3enc")
        self.app.project.setSettings(self.settings)
        self.app.publish_button.set_sensitive(False)

        #Auto-completion
        if unsecure_storing :
            self.widgets["checkbutton1"].set_label("Remember me ! Warning : \
storage will not be secure. Install python-gnomekeyring.")
            if self.app_settings.login:
                self.username.set_text(self.app_settings.login)
                self.password.set_text(self.app_settings.password)
        elif "pitivi" in gk.list_keyring_names_sync():
            item_keys = gk.list_item_ids_sync('pitivi')
            gk.unlock_sync('pitivi', 'gkpass')
            item_info = gk.item_get_info_sync('pitivi', item_keys[0])
            if item_info :
                self.username.set_text(item_info.get_display_name())
                self.password.set_text(item_info.get_secret())
            gk.lock_sync('pitivi')

        self.remember_me = False
        self.description = self.widgets["description"]
        self.tags = self.widgets["tags"]
        self.categories = gtk.combo_box_new_text()
        self.widgets["table2"].attach(self.categories, 1, 2, 3, 4)
        self.categories.show()
        self.categories.set_title("Choose a category")
        self.hbox = gtk.HBox()
        self.progressbar = gtk.ProgressBar()
        self.stopbutton = gtk.ToolButton(gtk.STOCK_CANCEL)
        self.hbox.pack_start(self.progressbar)
        self.hbox.pack_start(self.stopbutton)
        self.taglist = []

        # Assistant pages
        self.login_page = self.window.get_nth_page(0)
        self.metadata_page = self.window.get_nth_page(1)
        self.render_page = self.window.get_nth_page(2)
        self.announce_page = self.window.get_nth_page(3)

        for e in catlist:
            self.categories.append_text(e)

        self.description.get_buffer().connect("changed", self._descriptionChangedCb)
        self.categories.connect("changed", self._categoryChangedCb)
        self.stopbutton.connect('clicked', self._finishCb)
        self.mainquitsignal = self.app.connect('destroy', self._mainQuitCb)

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
            "private": False,
            "category": None,
            "tags": "",
        }
        self.has_started_rendering = False

    def _shutDown(self):
        self.debug("shutting down")
        self.app.project.setSettings(self.oldsettings)
        self.app.publish_button.set_sensitive(True)
        self.app.handler_disconnect(self.mainquitsignal)

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
        self.yt.stop()
        self.window.destroy()
        self.destroy()

    def _storePassword(self):
        if unsecure_storing:
            self.app_settings.login = self.username.get_text()
            self.app_settings.password = self.password.get_text()
            self.app_settings.storeSettings()
        else :
            if "pitivi" not in gk.list_keyring_names_sync():
                gk.create_sync('pitivi', 'gkpass')
            atts = {'username':'pitivi',
                    'server':'Youtube',
                    'service':'HTTP',
                    'port':'80',
                   }
            a = gk.item_create_sync('pitivi', gk.ITEM_GENERIC_SECRET,
                self.username.get_text(), atts, self.password.get_text(), True)

    def _mainQuitCb(self, ignored):
        self.yt.stop()
        self.window.destroy()
        self.destroy()

    def _deleteEventCb(self, window, event):
        self.debug("delete event")
        self._shutDown()

    def _cancelCb(self, ignored):
        self.debug("cancel event")
        self._shutDown()

    def _rememberMeCb(self, button):
        self.remember_me = False
        if button.get_active():
            self.remember_me = True

    def _loginClickedCb(self, *args):
        self.debug("login clicked")
        self.login_status.set_text("Logging in...")
        # TODO: This should activate a throbber
        self.yt.authenticate_with_password(self.username.get_text(), self.password.get_text(), self._loginResultCb)

    def _loginResultCb(self, result):
        # TODO: The throbber should now be deactivated
        status = result[0]
        if status == 'good':
            status, login_token = result
            if self.remember_me:
                self._storePassword()
            self.login_status.set_text("Logged in")
            self.window.set_page_complete(self.login_page, True)
            self.window.set_current_page(self.window.get_current_page() + 1)
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

    def _titleChangedCb(self, entry):
        self.metadata["title"] = entry.get_text()
        self._update_metadata_page_complete()

    def _descriptionChangedCb(self, buffer):
        self.metadata["description"] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter())
        self._update_metadata_page_complete()

    def _newTagCb(self, entry):
        letter_set = frozenset(ascii_lowercase + ascii_uppercase)
        tab = maketrans(ascii_lowercase + ascii_uppercase, ascii_lowercase * 2)
        deletions = ''.join(ch for ch in map(chr,range(256)) if ch not in letter_set)
        text = translate(entry.get_text(), tab, deletions)
        if len(text) < 2:
            entry.set_sensitive(False)
            entry.set_text(" One-letter tags ain't admitted")
            timeout_add(1000, entry.set_text, "")
            timeout_add (1000, entry.set_sensitive, True)
            return

        if self.metadata["tags"] != "" and text != "" and self.metadata["tags"].count(",") < 6 and text not in self.taglist:
            self.metadata["tags"] = self.metadata["tags"] + ", " + text
            self.taglist.append(text)

        elif text != "" and self.metadata["tags"].count(",") < 6 and text not in self.taglist:
            self.metadata["tags"] = text
            self.taglist.append(text)
        entry.set_text('')

    def _categoryChangedCb(self, combo):
        self.metadata["category"] = combo.get_active_text()

    def _prepareCb(self, assistant, page):
        if page == self.render_page and not self.has_started_rendering:
            self._startRenderAndUpload()

    def _destroyCb (self, ignored):
        self._shutDown()

    def _changeStatusCb (self, button):
        if button.get_active():
            self.metadata["private"] = True
        else:
            self.metadata["private"] = False

    def _startRenderAndUpload(self):

        self.has_started_rendering = True
        
        # Start uploading:
        self.yt.upload(lambda: PipeWrapper(open(self.fifoname, 'rb')), self.metadata, self._uploadDoneCb)

        # Start rendering:
        self.startAction()
        self.app.sourcelist.pack_end(self.hbox, False, False)
        self.hbox.show_all()
        self.progressbar.set_fraction(0)
        self.visible = True

    def updatePosition(self, fraction, text):
        self.progressbar.set_fraction(fraction)
        if self.visible:
            self.window.destroy()
            self.visible = False
        if text is not None and fraction < 0.99:
            self.progressbar.set_text(_("About %s left") % text)
        elif fraction < 0.05:
            self.progressbar.set_text(_("Starting rendering"))
        elif fraction > 0.99:
            self.progressbar.set_text(_("Rendering done, finishing uploading"))
            self.progressbar.set_pulse_step (0.05)
            self.over = False
            timeout_add (400, self._pulseCb)

    def _pulseCb(self):
        self.progressbar.pulse()
        if not self.over :
            timeout_add (400, self._pulseCb)
        return False

    def _finishCb(self, unused):
        self.hbox.destroy()
        self._shutDown()

    def _uploadDoneCb(self, result):
        self.entry = gtk.Entry()
        if result[0] == "good":
            status, new_entry = result
            self.entry.set_text(new_entry.GetSwfUrl().split ("?")[0])
        else:
            status, exception = result
            self.entry.set_text("error : " + status + exception)
        self.over = True
        self.progressbar.destroy()
        self.hbox.pack_start (self.entry)
        self.entry.show()
