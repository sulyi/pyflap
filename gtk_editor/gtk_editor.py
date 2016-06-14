#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# gtk_editor -- a GUI for graph_tool made by Tiago de Paula Peixoto
#
# Copyright (C) 2016 Ákos Sülyi <sulyi.gbox@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from graph_tool import *
from graph_tool.stats import label_parallel_edges, remove_labeled_edges

from graph_tool.draw import gtk_draw
from graph_tool.draw.gtk_draw import VertexMatrix

from graph_tool.draw.cairo_draw import *
from graph_tool.draw.cairo_draw import _vdefaults, _edefaults


class GraphEditorWindow(Gtk.Window):
    r"""Interactive GTK+ window containing a :class:`~Gtk.Notebook` that has
    :class:`~GraphEditorWidget` pages.

    Parameters
    ----------
    geometry : tuple
        Widget geometry.
    title : str
        The title of the window.

    Notes
    -----

    At the top there's a toolbar with seven buttons. First four are quite
    self-explanatory: New, Load, Save and Save as, then three "mode" buttons
    select, place nodes and place edges (see :class:`~GraphEditorWidget`).

    On the left there are two lists. In the upper one each row corresponds
    with a selected element (vertex or edge). Each row has three columns:
    index, label and a checkbox. Checking the checkbox "preselects"
    the corresponding element. Below the selected lis there are a button
    and a checkbox. The preselected vertices or edges may be removed by
    pressing this button. And checking this checkbox "preselects" all
    elements in the selected list.

    In the lower list each row corresponds with an element connected to
    a selected one. Therefore if there are vertices selected there are
    edges in the connected list and vice versa. Each row in the connected
    list has the same three columns as the selected list and has a button
    and a checkbox below it. Although pressing this button selects
    the "preselected" elements. A subset of the old selected list will
    appear in the connected list and the state of "preselection" will be
    preserved.

    """

    class TabLabel(Gtk.Box):
        r"""A box with a label and a close button."""
        def __init__(self, title=None):
            Gtk.Box.__init__(self, False, 3)
            self.close_btn = Gtk.Button()
            self.label = Gtk.Label(title if title is not None else "untitled")

            image = Gtk.Image()
            image.set_from_stock(Gtk.STOCK_CLOSE, Gtk.IconSize.MENU)

            self.close_btn.set_image(image)
            self.close_btn.set_relief(Gtk.ReliefStyle.NONE)

            self.pack_start(self.label, expand=True, fill=True, padding=0)
            self.pack_end(self.close_btn, expand=False, fill=False, padding=0)
            self.show_all()

    def __init__(self, geometry, title):
        print("===> " + title + " <===", file=sys.stderr)
        Gtk.Window.__init__(self, title=title)
        icon = GdkPixbuf.Pixbuf.new_from_file('%s/graph-tool-logo.svg' %
                                              os.path.dirname(gtk_draw.__file__))
        # IDEA: os.path.join(os.path.dirname(gtk_draw.__file__), 'graph-tool-logo.svg')
        self.set_icon(icon)
        self.set_default_size(geometry[0], geometry[1])

        self._mode = GraphEditorWidget.modes.select
        # CheckButton.set_active (sadly) emits clicked event
        self._allow_select_all_select = True
        self._allow_select_all_remove = True

        # init layout
        self.v_layout = Gtk.VBox(False, 0)
        self.h_layout = Gtk.HBox(False, 0)
        # NOTE: find a way for Paned to work
        # self.h_layout = Gtk.HPaned()

        # setup notebook
        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)

        self.notebook.connect("switch-page", self.page_changed_event)

        # init toolbar
        self.toolbar = Gtk.Toolbar()

        # storage placeholders
        self.vertex_store = None
        self.edge_store = None
        self.selected_vertices_filter = None
        self.selected_edges_filter = None

        # setup left sidebar
        self.selected_tree_view = Gtk.TreeView()
        self.connected_tree_view = Gtk.TreeView()

        self.selected_tree_view.set_hover_selection(True)
        self.connected_tree_view.set_hover_selection(True)

        selected_selection = self.selected_tree_view.get_selection()
        connected_selection = self.connected_tree_view.get_selection()

        selected_selection.connect("changed", self.highlight_prepicked_event)
        connected_selection.connect("changed", self.highlight_prepicked_event)

        # setup picked sidebar
        label_cell = Gtk.CellRendererText()
        remove_cell = Gtk.CellRendererToggle()
        remove_cell.connect("toggled", self.preselect_to_remove_event)

        index_column = Gtk.TreeViewColumn("#", Gtk.CellRendererText(), text=0)
        label_column = Gtk.TreeViewColumn("Label", label_cell)
        remove_column = Gtk.TreeViewColumn("", remove_cell, active=1)

        label_column.set_cell_data_func(label_cell, self._render_label_cell)
        label_column.set_expand(True)
        remove_column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        remove_column.set_fixed_width(20)

        self.selected_tree_view.insert_column(index_column, 0)
        self.selected_tree_view.insert_column(label_column, 1)
        self.selected_tree_view.insert_column(remove_column, 2)

        picked_scrollable_pane = Gtk.ScrolledWindow()
        picked_scrollable_pane.set_vexpand(True)
        picked_scrollable_pane.add(self.selected_tree_view)

        # setup picked last row
        remove_btn = Gtk.Button("Remove")
        select_all_remove_label = Gtk.Label("Select all")
        self._select_all_remove_check_btn = Gtk.CheckButton()

        remove_btn.connect("clicked", self.remove_event)
        self._select_all_remove_check_btn.connect("clicked", self.preselect_all_to_remove_event)

        # setup connected sidebar
        label_cell = Gtk.CellRendererText()
        select_cell = Gtk.CellRendererToggle()
        select_cell.connect("toggled", self.preselect_to_select_event)

        index_column = Gtk.TreeViewColumn("#", Gtk.CellRendererText(), text=0)
        label_column = Gtk.TreeViewColumn("Label", label_cell)
        select_column = Gtk.TreeViewColumn("", select_cell, active=1)

        label_column.set_cell_data_func(label_cell, self._render_label_cell)
        label_column.set_expand(True)
        select_column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        select_column.set_fixed_width(20)

        self.connected_tree_view.insert_column(index_column, 0)
        self.connected_tree_view.insert_column(label_column, 1)
        self.connected_tree_view.insert_column(select_column, 2)

        connected_scrollable_pane = Gtk.ScrolledWindow()
        connected_scrollable_pane.set_vexpand(True)
        connected_scrollable_pane.add(self.connected_tree_view)

        # setup connected last row
        select_btn = Gtk.Button("Select")
        select_all_select_label = Gtk.Label("Select all")
        self._select_all_select_check_btn = Gtk.CheckButton()

        select_btn.connect("clicked", self.select_event)
        self._select_all_select_check_btn.connect("clicked", self.preselect_all_to_select_event)

        # setup toolbar
        toolbar_icon_size = Gtk.IconSize.SMALL_TOOLBAR
        valid, icon_width, icon_height = Gtk.IconSize.lookup(toolbar_icon_size)

        self.toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        self.toolbar.set_icon_size(toolbar_icon_size)

        new_btn = Gtk.ToolButton(Gtk.STOCK_NEW)
        open_btn = Gtk.ToolButton(Gtk.STOCK_OPEN)
        save_btn = Gtk.ToolButton(Gtk.STOCK_SAVE)
        save_as_btn = Gtk.ToolButton(Gtk.STOCK_SAVE_AS)

        # mode buttons
        select_mode_btn = Gtk.RadioToolButton()
        place_node_mode_btn = Gtk.RadioToolButton.new_from_widget(select_mode_btn)
        place_edge_mode_btn = Gtk.RadioToolButton.new_from_widget(select_mode_btn)

        new_btn.set_tooltip_text("New")
        open_btn.set_tooltip_text("Open")
        save_btn.set_tooltip_text("Save")
        save_as_btn.set_tooltip_text("Save as")

        new_btn.set_is_important(True)
        open_btn.set_is_important(True)
        save_btn.set_is_important(True)
        save_as_btn.set_is_important(True)

        icon = Gdk.Cursor(Gdk.CursorType.ARROW).get_image()
        select_mode_btn.set_icon_widget(Gtk.Image.new_from_pixbuf(icon))
        icon = GdkPixbuf.Pixbuf.new_from_file_at_size('%s/place-node.svg' % os.path.dirname(__file__),
                                                      icon_width, icon_height)
        # IDEA: os.path.join(os.path.dirname(__file__), 'place-node.svg')
        place_node_mode_btn.set_icon_widget(Gtk.Image.new_from_pixbuf(icon))
        icon = GdkPixbuf.Pixbuf.new_from_file_at_size('%s/place-edge.svg' % os.path.dirname(__file__),
                                                      icon_width, icon_height)
        # IDEA: os.path.join(os.path.dirname(__file__), 'place-edge.svg')
        place_edge_mode_btn.set_icon_widget(Gtk.Image.new_from_pixbuf(icon))

        select_mode_btn.set_tooltip_text("Select and move")
        place_node_mode_btn.set_tooltip_text("Place nodes")
        place_edge_mode_btn.set_tooltip_text("Place edges")

        new_btn.connect("clicked", self.new_tab_event)
        open_btn.connect("clicked", self.open_tab_event)
        save_btn.connect("clicked", self.save_current_tab_event)
        save_as_btn.connect("clicked", self.save_as_current_tab_event)

        select_mode_btn.connect("clicked", self.mode_button_clicked_event, GraphEditorWidget.modes.select)
        place_node_mode_btn.connect("clicked", self.mode_button_clicked_event, GraphEditorWidget.modes.place_node)
        place_edge_mode_btn.connect("clicked", self.mode_button_clicked_event, GraphEditorWidget.modes.place_edge)

        self.toolbar.insert(new_btn, 0)
        self.toolbar.insert(open_btn, 1)
        self.toolbar.insert(Gtk.SeparatorToolItem(), 2)
        self.toolbar.insert(save_btn, 3)
        self.toolbar.insert(save_as_btn, 4)
        self.toolbar.insert(Gtk.SeparatorToolItem(), 5)
        self.toolbar.insert(select_mode_btn, 6)
        self.toolbar.insert(place_node_mode_btn, 7)
        self.toolbar.insert(place_edge_mode_btn, 8)

        # setup layout
        v_picked_box = Gtk.VBox(False, 0)
        v_connected_box = Gtk.VBox(False, 0)
        v_tree_view_paned = Gtk.VPaned()

        v_tree_view_paned.set_size_request(150, -1)

        h_last_row = Gtk.HBox(False, 0)

        h_last_row.pack_start(remove_btn, False, False, 2)
        h_last_row.pack_end(self._select_all_remove_check_btn, False, False, 0)
        h_last_row.pack_end(select_all_remove_label, False, False, 2)

        v_picked_box.pack_start(picked_scrollable_pane, True, True, 0)
        v_picked_box.pack_start(h_last_row, False, False, 2)

        h_last_row = Gtk.HBox(False, 0)

        h_last_row.pack_start(select_btn, False, False, 2)
        h_last_row.pack_end(self._select_all_select_check_btn, False, False, 0)
        h_last_row.pack_end(select_all_select_label, False, False, 2)

        v_connected_box.pack_start(connected_scrollable_pane, True, True, 0)
        v_connected_box.pack_start(h_last_row, False, False, 2)

        v_tree_view_paned.pack1(v_picked_box, True, True)
        v_tree_view_paned.pack2(v_connected_box, True, True)

        self.h_layout.pack_start(v_tree_view_paned, False, False, 0)
        self.h_layout.pack_end(self.notebook, True, True, 0)

        # self.h_layout.pack1(v_tree_view_paned, False, False)
        # self.h_layout.pack2(self.notebook, True, True)

        self.v_layout.pack_start(self.toolbar, False, False, 0)
        self.v_layout.pack_end(self.h_layout, True, True, 0)
        self.v_layout.show_all()
        self.add(self.v_layout)

    @staticmethod
    def _load_graph(file_name):
        print("Loading '%s'..." % file_name, file=sys.stderr, flush=True)
        g = load_graph(file_name)
        # after load
        if "x" in g.vertex_properties and "x" in g.vertex_properties:
            pos = group_vector_property([g.vertex_properties["x"], g.vertex_properties["y"]])

            g.vertex_properties.properties.pop("x")
            g.vertex_properties.properties.pop("y")
        elif "x" in g.vertex_properties:
            pos = group_vector_property([g.vertex_properties["x"], g.new_vertex_property("double", 0.)])

            g.vertex_properties.properties.pop("x")
        elif "y" in g.vertex_properties:
            pos = group_vector_property([g.new_vertex_property("double", 0.), g.vertex_properties["y"]])

            g.vertex_properties.properties.pop("y")
        else:
            pos = None

        return g, pos

    @staticmethod
    def _save_graph(g, pos, file_name):
        print("Saving '%s'..." % file_name, file=sys.stderr, flush=True)
        # before save
        pos_x, pos_y = ungroup_vector_property(pos, [0, 1])
        g.vertex_properties["x"] = pos_x
        g.vertex_properties["y"] = pos_y

        g.save(file_name)

    @staticmethod
    def _vertex_from_cell(i, g):
        try:
            return g.vertex(i)
        except ValueError:
            return None

    @staticmethod
    def _edge_from_cell(source, target, index, g):
        return next((edge for edge in g.edge(source, target, all_edges=True)
                     if g.edge_index[edge] == index), None)

    @staticmethod
    def _is_vertex_selected(model, tree_iter, tab):
        i, = model.get(tree_iter, 0)
        vertex = GraphEditorWindow._vertex_from_cell(i, tab.g)
        return tab.selected_vertices[vertex]

    @staticmethod
    def _is_edge_selected(model, tree_iter, tab):
        i, s, t = model.get(tree_iter, 0, 2, 3)
        edge = GraphEditorWindow._edge_from_cell(s, t, i, tab.g)
        return tab.selected_edges[edge]

    def _save_tab(self, target_tab):
        if target_tab.file_name is None:
            target_tab.file_name = self._pick_file_dialog(save=True)
        if target_tab.file_name is not None:
            GraphEditorWindow._save_graph(target_tab.g, target_tab.pos, target_tab.file_name)
            target_tab.emit("graph-changed", False)

    def _close_tab(self, target_tab):
        if target_tab.is_changed():
            question = "This tab has changed.\nWould you like to save it before closing it?"
            title = "Closing tab..."
            response = self._yes_no_dialog(title, question)
            if response:
                self._save_tab(target_tab)
        else:
            response = True

        if response is not None:
            self.notebook.remove(target_tab)
            return False
        return True

    def _preselect(self, cell, path, model):
        tab = self.get_current_tab()
        # tree_iter = model.get_iter(Gtk.TreePath.new_from_string(path))
        # model.set_value(tree_iter, 1, not cell.get_active())
        model[path][1] = not cell.get_active()
        if model == self.selected_vertices_filter:
            # i, to = model.get(tree_iter, 0, 1)
            i, to = model[path]
            if tab.preselected_vertices is None:
                tab.preselected_vertices = tab.g.new_vertex_property("bool", False)
            tab.preselected_vertices[GraphEditorWindow._vertex_from_cell(i, tab.g)] = to
            if not any(tab.preselected_vertices.fa):
                tab.preselected_vertices = None
        elif model == self.selected_edges_filter:
            # i, to, s, t = model.get(tree_iter, 0, 1, 2, 3)
            i, to, s, t = model[path]
            if tab.preselected_edges is None:
                tab.preselected_edges = tab.g.new_edge_property("bool", False)
            tab.preselected_edges[GraphEditorWindow._edge_from_cell(s, t, i, tab.g)] = to
            if not any(tab.preselected_edges.fa):
                tab.preselected_edges = None
        tab.queue_draw()

    def _preselect_all(self, model, to):
        tab = self.get_current_tab()

        for row in model:
            model[row.path][1] = to

        if to:
            if model == self.selected_vertices_filter:
                tab.preselected_vertices = tab.selected_vertices.copy()
            elif model == self.selected_edges_filter:
                tab.preselected_edges = tab.selected_edges.copy()
        else:
            if model == self.selected_vertices_filter:
                tab.preselected_vertices = None
            elif model == self.selected_edges_filter:
                tab.preselected_edges = None
        tab.queue_draw()

    def _pick_file_dialog(self, save=False):
        dialog = Gtk.FileChooserDialog("Please choose a file", self,
                                       Gtk.FileChooserAction.OPEN,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                        Gtk.STOCK_SAVE if save else Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        # NOTE: implement filters
        # filter_text = Gtk.FileFilter()
        # filter_text.set_name("Text files")
        # filter_text.add_mime_type("text/plain")
        # dialog.add_filter(filter_text)

        response = dialog.run()

        file_name = None
        if response == Gtk.ResponseType.OK:
            file_name = dialog.get_filename()

        dialog.destroy()

        return file_name

    def _yes_no_dialog(self, title, message):
        dialog = Gtk.Dialog(title, self, 0,
                            (Gtk.STOCK_NO, Gtk.ResponseType.NO,
                             Gtk.STOCK_YES, Gtk.ResponseType.YES,
                             Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))

        dialog.set_default_size(150, 100)
        dialog.set_resizable(False)

        label = Gtk.Label(message)

        label.set_margin_top(10)
        label.set_margin_left(10)
        label.set_margin_bottom(10)
        label.set_margin_right(10)

        box = dialog.get_content_area()
        box.pack_start(label, True, True, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.YES:
            answer = True
        elif response == Gtk.ResponseType.NO:
            answer = False
        else:
            answer = None

        dialog.destroy()
        return answer

    def _render_label_cell(self, column, cell, model, tree_iter, data=None):
        tab = self.get_current_tab()
        txt = None
        if model == self.selected_vertices_filter:
            i, = model.get(tree_iter, 0)
            vertex = GraphEditorWindow._vertex_from_cell(i, tab.g)
            if vertex is not None:
                txt = tab.vprops["text"][vertex] if "text" in tab.vprops else ""
        elif model == self.selected_edges_filter:
            i, s, t = model.get(tree_iter, 0, 2, 3)
            edge = GraphEditorWindow._edge_from_cell(s, t, i, tab.g)
            if edge is not None:
                if "text" in tab.eprops:
                    txt = tab.eprops["text"][edge]
                if not txt:  # None or ""
                    txt = "(%d -> %d)" % (s, t)
        if txt is None:
            txt = "not found"
        cell.set_property("text", txt)

    def new_tab_event(self, widget):
        r"""Handles opening a new empty tab."""
        self.add_new_empty_tab()

    def open_tab_event(self, widget):
        r"""Handles opening a tab from file."""
        file_path = self._pick_file_dialog()
        if file_path is not None:
            self.load_graph_in_new_tab(file_path)

    def save_current_tab_event(self, widget):
        r"""Handles saving a tab."""
        self._save_tab(self.get_current_tab())

    def save_as_current_tab_event(self, widget):
        r"""Handles saving a tab as a new file."""
        file_name = self._pick_file_dialog(save=True)
        if file_name is not None:
            self.get_current_tab().file_name = file_name
            self._save_tab(self.get_current_tab())

    def close_tab_event(self, widget, tab):
        r"""Handles closing a tab."""
        self._close_tab(tab)

    def mode_button_clicked_event(self, widget, mode):
        r"""Handles click on mode buttons."""
        self._mode = mode
        for tab in self.notebook.get_children():
            tab.edit_mode = mode

    def page_changed_event(self, widget, tab, n):
        r"""Handles `switch-page` event."""
        self.vertex_store = Gtk.ListStore(int, bool)
        self.edge_store = Gtk.ListStore(int, bool, int, int)

        for vertex in tab.g.vertices():
            self.vertex_store.append([tab.g.vertex_index[vertex],
                                      False if tab.preselected_vertices is None else
                                      tab.preselected_vertices[vertex]])
        for edge in tab.g.edges():
            self.edge_store.append([tab.g.edge_index[edge],
                                    False if tab.preselected_edges is None else
                                    tab.preselected_edges[edge],
                                    edge.source(),
                                    edge.target()])

        self.selected_vertices_filter = self.vertex_store.filter_new()
        self.selected_edges_filter = self.edge_store.filter_new()

        self.selected_vertices_filter.set_visible_func(GraphEditorWindow._is_vertex_selected, tab)
        self.selected_edges_filter.set_visible_func(GraphEditorWindow._is_edge_selected, tab)

        self.picked_change_event(tab)

    def graph_changed_event(self, tab, state, notebook):
        r"""Handles `graph-changed` event."""
        header = notebook.get_tab_label(tab)
        if state:
            header.label.set_markup("<span color='red'>%s</span>" % header.label.get_text())
            self.page_changed_event(notebook, tab, notebook.page_num(tab))
        else:
            header.label.set_markup(header.label.get_text())

    def picked_change_event(self, tab):
        r"""Handles `picked-changed` event."""
        if tab.picked is None:
            self.selected_tree_view.set_model(None)
            self.connected_tree_view.set_model(None)
        else:
            # keep stores persistent
            for row in self.vertex_store:
                i, = self.vertex_store.get(row.iter, 0)
                vertex = GraphEditorWindow._vertex_from_cell(i, tab.g)
                if tab.preselected_vertices is None or not tab.preselected_vertices[vertex]:
                    self.vertex_store[row.path][1] = False

            for row in self.edge_store:
                i, s, t = self.edge_store.get(row.iter, 0, 2, 3)
                edge = GraphEditorWindow._edge_from_cell(s, t, i, tab.g)
                if tab.preselected_edges is None or not tab.preselected_edges[edge]:
                    self.edge_store[row.path][1] = False

            self.selected_vertices_filter.refilter()
            self.selected_edges_filter.refilter()
            if tab.picked is None:
                all_select_set = False
                all_remove_set = False
            elif (isinstance(tab.picked, Vertex) or
                  (isinstance(tab.picked, PropertyMap) and tab.picked.key_type() == 'v')):
                all_select_set = all(row[1] for row in self.selected_edges_filter)
                all_remove_set = all(row[1] for row in self.selected_vertices_filter)
                if self.selected_tree_view.get_model() != self.selected_vertices_filter:
                    self.selected_tree_view.set_model(self.selected_vertices_filter)
                if self.connected_tree_view.get_model() != self.selected_edges_filter:
                    self.connected_tree_view.set_model(self.selected_edges_filter)
            elif (isinstance(tab.picked, Edge) or
                    (isinstance(tab.picked, PropertyMap) and tab.picked.key_type() == 'e')):
                all_select_set = all(row[1] for row in self.selected_vertices_filter)
                all_remove_set = all(row[1] for row in self.selected_edges_filter)
                if self.selected_tree_view.get_model() != self.selected_edges_filter:
                    self.selected_tree_view.set_model(self.selected_edges_filter)
                if self.connected_tree_view.get_model() != self.selected_vertices_filter:
                    self.connected_tree_view.set_model(self.selected_vertices_filter)
            else:
                # things just got awkward...
                all_select_set = self._select_all_select_check_btn.get_active()
                all_remove_set = self._select_all_remove_check_btn.get_active()

            if all_select_set != self._select_all_select_check_btn.get_active():
                self._allow_select_all_select = False
                self._select_all_select_check_btn.set_active(all_select_set)
            if all_remove_set != self._select_all_remove_check_btn.get_active():
                self._allow_select_all_remove = False
                self._select_all_remove_check_btn.set_active(False)

    def preselect_to_remove_event(self, cell, path):
        r"""Sets vertex or edge corresponding to ``cell`` in
        :attr:`~GraphEditorWindow.selected_tree_view` as preselected."""
        # can't tell tree views apart
        model = self.selected_tree_view.get_model()
        if self._select_all_remove_check_btn.get_active():
            self._allow_select_all_remove = False
            self._select_all_remove_check_btn.set_active(False)

        self._preselect(cell, path, model)

    def preselect_to_select_event(self, cell, path):
        r"""Sets vertex or edge corresponding to ``cell`` in
        :attr:`~GraphEditorWindow.connected_tree_view` as preselected."""
        # can't tell tree views apart
        model = self.connected_tree_view.get_model()
        if self._select_all_select_check_btn.get_active():
            self._allow_select_all_select = False
            self._select_all_select_check_btn.set_active(False)

        self._preselect(cell, path, model)

    def preselect_all_to_remove_event(self, widget):
        r"""Sets all vertex or edge preselected in :attr:`~GraphEditorWindow.connected_tree_view`."""
        if self._allow_select_all_remove:
            model = self.selected_tree_view.get_model()
            if model is not None:
                self._preselect_all(model, widget.get_active())
        # due to this can't merge with select_all_select_event
        self._allow_select_all_remove = True

    def preselect_all_to_select_event(self, widget):
        r"""Sets all vertex or edge preselected in :attr:`~GraphEditorWindow.selected_tree_view`."""
        if self._allow_select_all_select:
            model = self.connected_tree_view.get_model()
            if model is not None:
                self._preselect_all(model, widget.get_active())
        # due to this can't merge with select_all_remove_event
        self._allow_select_all_select = True

    def highlight_prepicked_event(self, tree_selection):
        r"""Highlights vertex or edge corresponding to row the cursor is currently over
        in :attr:`~selected_tree_view` or :attr:`~connected_tree_view`."""
        tab = self.get_current_tab()
        model, tree_iter = tree_selection.get_selected()
        if tree_iter is not None:
            if model == self.selected_vertices_filter:
                i, = model.get(tree_iter, 0)
                tab.prepicked = GraphEditorWindow._vertex_from_cell(i, tab.g)
            elif model == self.selected_edges_filter:
                i, s, t = model.get(tree_iter, 0, 2, 3)
                tab.prepicked = GraphEditorWindow._edge_from_cell(s, t, i, tab.g)
        else:
            tab.prepicked = None
        tab.queue_draw()

    def select_event(self, widget):
        r"""Changes selection to preselection."""
        tab = self.get_current_tab()
        model = self.connected_tree_view.get_model()
        if model == self.selected_vertices_filter and tab.preselected_vertices is not None:
            tab.picked = tab.preselected_vertices.copy()
            tab.selected_vertices = tab.preselected_vertices.copy()
            tab.preselected_vertices = None
            tab.emit("picked-changed")
        elif model == self.selected_edges_filter and tab.preselected_edges is not None:
            tab.picked = tab.preselected_edges.copy()
            tab.selected_edges = tab.preselected_edges.copy()
            tab.preselected_edges = None
            tab.emit("picked-changed")

    def remove_event(self, widget):
        r"""Removes preselected vertices or edges."""
        # TODO: update selected
        tab = self.get_current_tab()
        model = self.selected_tree_view.get_model()
        if model == self.selected_vertices_filter:
            remove = []
            reinit_vertex_matrix = False
            for row in model:
                if model[row.path][1]:
                    # tree_iter = model.get_iter(row.path)
                    # i, = model.get(tree_iter, 0)
                    i = model[row.path][0]
                    vertex = GraphEditorWindow._vertex_from_cell(i, tab.g)
                    if not reinit_vertex_matrix and tab.vertex_matrix is not None:
                        reinit_vertex_matrix = True
                    remove.append(vertex)

            # XXX: vertex properties are not trimmed when last vertex is included
            # XXX: removing non-continuous list of vertices while last one is included messes up vertex properties
            tab.g.remove_vertex(remove)
            if reinit_vertex_matrix:
                tab.init_vertex_matrix()
        elif model == self.selected_edges_filter:
            for row in model:
                if model[row.path][1]:
                    # tree_iter = model.get_iter(row.path)
                    # i, s, t = model.get(tree_iter, 0, 2, 3)
                    i, _, s, t = model[row.path]
                    # XXX: removing an edge having both source and target the same as another messes up edge properties
                    tab.g.remove_edge(GraphEditorWindow._edge_from_cell(s, t, i, tab.g))
        tab.emit("graph-changed", True)

    def cleanup(self):
        r"""Closes each tab. If it's changed saves it."""
        pages = self.notebook.get_children()
        if pages:
            # return all(self._close_tab(tab) for tab in pages)
            # cancels event at first hiccup
            all_closed = True
            for tab in pages:
                if self._close_tab(tab):
                    all_closed = False
            return not all_closed
        else:
            print("All clear!", file=sys.stderr)
            return False

    def destroy(self):
        return self.cleanup()

    def __del__(self):
        self.cleanup()
        print("The End.", file=sys.stderr)

    def get_current_tab(self):
        r"""Returns the current tab."""
        return self.notebook.get_nth_page(self.notebook.get_current_page())

    def add_new_empty_tab(self):
        r"""Adds a new empty tab."""
        print("Opening new graph...", file=sys.stderr, flush=True)
        g = Graph()
        pos = g.new_vertex_property("vector<double>")
        self.add_new_tab(g, pos)

    def add_new_tab(self, g, pos, file_name=None):
        if pos is None or not all(pos):
            pos = sfdp_layout(g, pos=pos)

        tab = GraphEditorWidget(g, pos, edit_mode=self._mode, file_name=file_name)

        header = self.TabLabel(file_name)
        header.close_btn.connect("clicked", self.close_tab_event, tab)

        tab.connect("picked-changed", self.picked_change_event)
        tab.connect("graph-changed", self.graph_changed_event, self.notebook)  # paint label red
        tab.show()

        self.notebook.prepend_page(tab, header)
        self.notebook.set_current_page(self.notebook.page_num(tab))
        self.notebook.set_focus_child(tab)
        # self.notebook.get_tab_label(tab) returns header

    def load_graph_in_new_tab(self, file_path):
        r"""Loads a graph from file and adds it to a new tab."""
        g, pos = GraphEditorWindow._load_graph(file_path)
        file_name = os.path.basename(file_path)
        self.add_new_tab(g, pos, file_name)


class GraphEditorWidget(Gtk.DrawingArea):
    r"""Interactive GTK+ widget displaying a given graph.

    Parameters
    ----------
    g : :class:`~graph_tool.Graph`
        Graph to be drawn.
    pos : :class:`~graph_tool.PropertyMap`
        Vector-valued vertex property map containing the x and y coordinates of
        the vertices.
    vprops : dict (optional, default: ``None``)
        Dictionary with the vertex properties. Individual properties may also be
        given via the ``vertex_<prop-name>`` parameters, where ``<prop-name>`` is
        the name of the property. Values in :attr:`~g.vertex_properties` are
        updated by them.
    eprops : dict (optional, default: ``None``)
        Dictionary with the edge properties. Individual properties may also be
        given via the ``edge_<prop-name>`` parameters, where ``<prop-name>`` is
        the name of the property. Values in :attr:`~g.edge_properties` are
        updated by them.
    vorder : :class:`~graph_tool.PropertyMap` (optional, default: ``None``)
        If provided, defines the relative order in which the vertices are drawn.
    eorder : :class:`~graph_tool.PropertyMap` (optional, default: ``None``)
        If provided, defines the relative order in which the edges are drawn.
    nodesfirst : bool (optional, default: ``False``)
        If ``True``, the vertices are drawn first, otherwise the edges are.
    fit_area : float  (optional, default: ``.95``)
        Fraction of the drawing area to fit the graph initially.
    bg_color : str or sequence (optional, default: ``None``)
        Background color. The default is white.
    max_render_time : int (optional, default: ``300``)
        Maximum amount of time (in milliseconds) spent rendering portions of
        the graph.
    highlight_color : tuple (optional, default: ``None``)
        Color of halo around highlighted vertices and edges.
        If ``None`` #EF2929 RGB color with 0.9 alpha is used.
    preselected_color: Color of halo around preselected vertices and edges.
        Default value is ``None``. That case #FFC323 RGB color with 0.5 alpha
        is used.
    edit_mode : int (optional, default: :attr:`~GraphEditorWidget.modes.select`)
        Initial value of :attr:`~GraphEditorWidget.edit_mode`.
    file_name : str (optional, default: ``None``)
        A name of the file to save the graph.
    modes : :class:`~GraphEditorWidget.Modes` (singleton)

    Signals
    -------
    graph-changed : Emitted when graph changes (e.g. new vertex or edge has been placed,
        position of a vertex has been changed).
    picked-changed : Emitted when selection has changed.

`   Notes
    -----

    Widget can work in three modes selection, edge and vertex placement. Any of the mode
    can be panned in vertically by scrolling and horizontally scrolling while holding
    the "shift" key. The graph may be zoomed by scrolling with the mouse wheel while
    holding down the "control" key or dragging a rectangle around the are while holding
    the "control" key. If the key "z" is pressed, the layout is zoomed to fit the selected
    vertices only. While holding down the "shift" key Vertices may be selected and deselected
    by pressing the left mouse button over them or dragging a rectangle around them. Edges
    may be selected by scrolling with the mouse wheel while the cursor is over a selected or
    highlighted vertex. Beware this will interfere with panning vertically.

    While :attr:`edit_mode` is equal to :attr:`~GraphEditorWidget.modes.select` or
    :attr:`~GraphEditorWidget.select`  the graph can be panned also by pressing
    the left mouse button outside any vertex and dragging.

    While :attr:`edit_mode` is equal to :attr:`~GraphEditorWidget.modes.select` vertices
    can be moved by pressing the left mouse button over one of the selected vertices and
    dragging them.

    While :attr:`edit_mode` is equal to :attr:`~GraphEditorWidget.place_node` a new vertex
    can be added to the graph by pressing the left mouse button. The newly added vertex
    may be dragged along before releasing the button.

    While :attr:`edit_mode` is equal to :attr:`~GraphEditorWidget.place_edge` new edge can be
    added to the graph by pressing the left mouse button over the source and releasing it
    over the target vertex. If the mouse button is not released over any vertex no edge will
    be added, but if it is released over the same vertex a self-loop will be added.

    Pressing the right mouse button will cancel every action going on (e.g. any rectangle
    being dragged, any vertex being moved if it is newly added than it will be removed).
    """

    class Modes:
        r"""An enum of modes."""
        select, place_node, place_edge = range(3)

    __gsignals__ = {"graph-changed": (gobject.SignalFlags.RUN_FIRST, None, (bool,)),
                    "picked-changed": (gobject.SignalFlags.RUN_FIRST, None, ())}
    modes = Modes()

    def __init__(self, g, pos, vprops=None, eprops=None, vorder=None,
                 eorder=None, nodesfirst=False, fit_area=0.95, bg_color=None,
                 max_render_time=300, highlight_color=None, preselected_color=None,
                 edit_mode=modes.select, file_name=None, **kwargs):
        Gtk.DrawingArea.__init__(self)

        vprops = {} if vprops is None else vprops
        eprops = {} if eprops is None else eprops

        props, kwargs = parse_props("vertex", kwargs)
        vprops.update(props)
        props, kwargs = parse_props("edge", kwargs)
        eprops.update(props)
        self.kwargs = kwargs

        vprops.update((key, value) for key, value in g.vp.items() if key not in vprops)
        eprops.update((key, value) for key, value in g.ep.items() if key not in eprops)

        self.g = g
        self.pos = pos
        self.vprops = vprops
        self.eprops = eprops
        self.vorder = vorder
        self.eorder = eorder
        self.nodesfirst = nodesfirst

        self._changed = False
        self.file_name = file_name
        self.edit_mode = edit_mode

        self.tmatrix = cairo.Matrix()  # position to surface
        self.smatrix = cairo.Matrix()  # surface to screen
        self.scale = 1.
        self.pointer = [0, 0]
        self.picked = None
        self.prepicked = None
        self.selected_vertices = g.new_vertex_property("bool", False)
        self.selected_edges = g.new_edge_property("bool", False)
        self.__no_edges = g.new_edge_property("bool", False)  # don't set any of it
        self.preselected_vertices = None
        self.preselected_edges = None
        self.highlight = g.new_vertex_property("bool", False)
        self.highlight_color = highlight_color
        self.prehighlight_color = preselected_color
        self.srect = None
        self.zrect = None
        self.new_edge = None
        self.drag_vector = [0, 0]
        self.is_moving = None
        self.is_panning = False
        self.vertex_matrix = None
        self.moved_picked = False
        self.pad = fit_area

        self.geometry = None
        self.base = None
        self.base_geometry = None
        self.background = None
        self.bg_color = bg_color if bg_color is not None else (1, 1, 1, 1)

        self.regenerate_offset = 0
        self.regenerate_max_time = max_render_time
        self.max_render_time = max_render_time
        self.lazy_regenerate = False

        self.connect("motion-notify-event", self.motion_notify_event)
        self.connect("button-press-event", self.button_press_event)
        self.connect("button-release-event", self.button_release_event)
        self.connect("scroll-event", self.scroll_event)
        self.connect("key-press-event", self.key_press_event)
        self.connect("key-release-event", self.key_release_event)
        self.connect("destroy-event", self.cleanup)

        self.set_events(Gdk.EventMask.EXPOSURE_MASK |
                        Gdk.EventMask.LEAVE_NOTIFY_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.BUTTON_MOTION_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.POINTER_MOTION_HINT_MASK |
                        Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.SMOOTH_SCROLL_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK |
                        Gdk.EventMask.KEY_RELEASE_MASK)

        self.set_property("can-focus", True)
        self.connect("draw", self.draw)

        try:
            self.zoom_gesture = Gtk.GestureZoom.new(self)
            self.zoom_gesture.connect("begin", self.zoom_begin)
            self.zoom_gesture.connect("end", self.zoom_end)
            self.zoom_gesture.connect("scale_changed", self.scale_changed)

            self.rotate_gesture = Gtk.GestureRotate.new(self)
            self.rotate_gesture.connect("begin", self.rotate_begin)
            self.rotate_gesture.connect("end", self.rotate_end)
            self.rotate_gesture.connect("angle_changed", self.angle_changed)

            self.zoom_gesture.group(self.rotate_gesture)

            self.drag_gesture = Gtk.GestureDrag.new(self)
            self.drag_gesture.set_touch_only(True)
            self.drag_gesture.connect("begin", self.drag_gesture_begin)
            self.drag_gesture.connect("end", self.drag_gesture_end)
            self.drag_gesture.connect("drag_update", self.drag_gesture_update)
        except AttributeError:
            pass

        self.is_zooming = False
        self.zoom_scale = 1
        self.is_rotating = False
        self.angle = None
        self.is_drag_gesture = False
        self.drag_last = [0, 0]

    def is_changed(self):
        r"""Returns value of last `graph-changed` signal or ``False`` if there wasn't any."""
        return self._changed

    # NOTE: remove these if certain no need for them
    def cleanup(self):
        pass

    def __del__(self):
        self.cleanup()

    # Actual drawing

    def regenerate_surface(self, reset=False, complete=False):
        r"""Redraw the graph surface."""

        if reset:
            self.regenerate_offset = 0

        geometry = [self.get_allocated_width() * 3,
                    self.get_allocated_height() * 3]

        if (self.base is None or self.base_geometry[0] != geometry[0] or
                self.base_geometry[1] != geometry[1] or reset):
            # self.base = cairo.ImageSurface(cairo.FORMAT_ARGB32,
            #                                *geometry)
            w = self.get_window()
            if w is None:
                return False
            self.base = w.create_similar_surface(cairo.CONTENT_COLOR_ALPHA,
                                                 *geometry)
            self.base_geometry = geometry
            self.regenerate_offset = 0

            m = cairo.Matrix()
            m.translate(self.get_allocated_width(),
                        self.get_allocated_height())
            self.smatrix = self.smatrix * m
            self.tmatrix = self.tmatrix * self.smatrix
            self.smatrix = cairo.Matrix()
            self.smatrix.translate(-self.get_allocated_width(),
                                   -self.get_allocated_height())

        cr = cairo.Context(self.base)
        if self.regenerate_offset == 0:
            cr.set_source_rgba(*self.bg_color)
            cr.paint()
        cr.set_matrix(self.tmatrix)
        mtime = -1 if complete else self.regenerate_max_time
        res = 5 * self.get_scale_factor()
        count = cairo_draw(self.g, self.pos, cr, self.vprops, self.eprops,
                           self.vorder, self.eorder, self.nodesfirst, res=res,
                           render_offset=self.regenerate_offset,
                           max_render_time=mtime, **self.kwargs)
        self.regenerate_offset = count
        self.lazy_regenerate = False

    def draw(self, da, cr):
        r"""Redraw the widget."""

        geometry = (self.get_allocated_width(),
                    self.get_allocated_height())

        if self.geometry is None:
            adjust_default_sizes(self.g, geometry, self.vprops, self.eprops)
            self.fit_to_window(ink=False)
            # HACK: highlighted self-loops are not aligned without control_points
            self.position_parallel_edges()
            self.regenerate_surface()
            self.geometry = geometry

        # QUESTION: is seamless property that prevents markers to be visible outside clipping area?
        # HACK: sometimes markers outside area are visible yet
        # e.g: when edge got highlighted while being outside,
        #      vertex got moved outside area
        # cr.rectangle(0, 0, *geometry)
        # cr.clip()

        cr.save()
        cr.set_matrix(self.smatrix)
        c1 = self.pos_to_device([0, 0], surface=True, cr=cr)
        c2 = self.pos_to_device([0, self.base_geometry[1]], surface=True, cr=cr)
        c3 = self.pos_to_device([self.base_geometry[0], 0], surface=True, cr=cr)
        c4 = self.pos_to_device(self.base_geometry, surface=True, cr=cr)
        c = [c1, c2, c3, c4]
        ul = [min([x[0] for x in c]), min([x[1] for x in c])]
        lr = [max([x[0] for x in c]), max([x[1] for x in c])]
        cr.restore()

        if ((ul[0] > 0 or lr[0] < geometry[0] or
             ul[1] > 0 or lr[1] < geometry[1]) or
                self.lazy_regenerate):
            self.regenerate_surface(reset=True)
        elif self.regenerate_offset > 0:
            self.regenerate_surface()

        if self.background is None:
            # draw checkerboard
            self.background = cairo.ImageSurface(cairo.FORMAT_ARGB32, 14, 14)
            bcr = cairo.Context(self.background)
            bcr.rectangle(0, 0, 7, 7)
            bcr.set_source_rgb(102. / 256, 102. / 256, 102. / 256)
            bcr.fill()
            bcr.rectangle(7, 0, 7, 7)
            bcr.set_source_rgb(153. / 256, 153. / 256, 153. / 256)
            bcr.fill()
            bcr.rectangle(0, 7, 7, 7)
            bcr.set_source_rgb(153. / 256, 153. / 256, 153. / 256)
            bcr.fill()
            bcr.rectangle(7, 7, 7, 7)
            bcr.set_source_rgb(102. / 256, 102. / 256, 102. / 256)
            bcr.fill()
            del bcr
            self.background = cairo.SurfacePattern(self.background)
            self.background.set_extend(cairo.EXTEND_REPEAT)

        cr.set_source(self.background)
        cr.paint()

        cr.save()
        cr.set_matrix(self.smatrix)
        cr.set_source_surface(self.base)
        cr.paint()
        cr.restore()

        # HACK: marker_size changes how control_points work, hence eprops needs to be copied
        if self.picked is not None:
            size = self.vprops.get("size", _vdefaults["size"])
            if isinstance(size, PropertyMap):
                size = size.fa.mean()
            if (isinstance(self.picked, Vertex) or
                    (isinstance(self.picked, PropertyMap) and self.picked.key_type() == 'v')):
                if self.preselected_edges is not None:
                    # draw preselected edges
                    # no vertices
                    vprops = self.vprops.copy()
                    vprops["color"] = (0., 0., 0., 0.)
                    vprops["fill_color"] = (0., 0., 0., 0.)
                    vprops["text_color"] = (0., 0., 0., 0.)
                    # fake edge halo
                    eprops = self.eprops.copy()
                    eprops["color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.5)
                    eprops["pen_width"] = 0.4 * size
                    eprops["seamless"] = True

                    if self.prehighlight_color is not None:
                        eprops["color"] = self.prehighlight_color

                    shown_edges = self.preselected_edges.copy()
                    if isinstance(self.prepicked, Edge):
                        shown_edges[self.prepicked] = False

                    u = GraphView(self.g, efilt=shown_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                # draw vertices and edges connected to selected ones
                self.highlight = self.selected_vertices.copy()
                vprops = self.vprops.copy()
                vprops["halo"] = self.highlight
                vprops["halo_color"] = (0.9372549019607843, 0.1607843137254902, 0.1607843137254902, .9)
                vprops["halo_size"] = 1.3
                eprops = self.eprops.copy()
                eprops["color"] = (0.9372549019607843, 0.1607843137254902, 0.1607843137254902, .9)
                eprops["seamless"] = True

                if self.highlight_color is not None:
                    vprops["halo_color"] = self.highlight_color
                    eprops["color"] = self.highlight_color

                infect_vertex_property(GraphView(self.g, directed=False),
                                       self.highlight, [True])

                shown_vertices = self.highlight.copy()
                if self.preselected_edges is not None:
                    shown_edges = self.g.new_edge_property("bool", np.logical_xor(self.preselected_edges.fa,
                                                                                  self.selected_edges.fa))
                else:
                    shown_edges = self.selected_edges.copy()

                self.highlight.fa = np.logical_xor(self.selected_vertices.fa,
                                                   self.highlight.fa)

                u = GraphView(self.g, vfilt=shown_vertices, efilt=shown_edges)

                eprops["pen_width"] = self.eprops.get("pen_width",
                                                      _edefaults["pen_width"])
                if isinstance(eprops["pen_width"], PropertyMap):
                    pw = eprops["pen_width"]
                    pw = u.own_property(pw.copy())
                    pw.fa *= 1.1
                else:
                    eprops["pen_width"] *= 1.1

                cr.save()
                cr.set_matrix(self.tmatrix * self.smatrix)
                cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                           self.eorder, self.nodesfirst)
                cr.restore()

                if isinstance(self.prepicked, Edge):
                    # draw prepicked edge
                    # no vertices
                    vprops = self.vprops.copy()
                    vprops["color"] = (0., 0., 0., 0.)
                    vprops["fill_color"] = (0., 0., 0., 0.)
                    vprops["text_color"] = (0., 0., 0., 0.)
                    # fake edge halo
                    eprops = self.eprops.copy()
                    eprops["color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.75)
                    eprops["pen_width"] = 0.4 * size
                    eprops["seamless"] = True

                    shown_edges = self.g.new_edge_property("bool", False)
                    shown_edges[self.prepicked] = True

                    u = GraphView(self.g, efilt=shown_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                # no edges
                eprops = {}
                if isinstance(self.prepicked, Vertex):
                    # draw prepicked vertices
                    vprops = self.vprops.copy()
                    vprops["halo"] = True
                    vprops["halo_color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.75)

                    shown_vertices = self.g.new_vertex_property("bool", False)
                    shown_vertices[self.prepicked] = True

                    u = GraphView(self.g, vfilt=shown_vertices, efilt=self.__no_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, self.eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                if self.preselected_vertices is not None:
                    # draw preselected vertices
                    vprops = self.vprops.copy()
                    vprops["halo"] = True
                    vprops["halo_color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.5)

                    if self.prehighlight_color is not None:
                        vprops["halo_color"] = self.prehighlight_color

                    shown_vertices = self.preselected_vertices.copy()
                    if isinstance(self.prepicked, Vertex):
                        shown_vertices[self.prepicked] = False

                    u = GraphView(self.g, vfilt=shown_vertices, efilt=self.__no_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, self.eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                    shown_vertices.fa = np.logical_xor(self.selected_vertices.fa,
                                                       self.preselected_vertices.fa)
                else:
                    shown_vertices.fa = self.selected_vertices.fa

                # draw selected vertices
                vprops = self.vprops.copy()
                vprops["halo"] = True

                if isinstance(self.prepicked, Vertex):
                    shown_vertices[self.prepicked] = False

                u = GraphView(self.g, vfilt=shown_vertices,
                              efilt=self.__no_edges)

                cr.save()
                cr.set_matrix(self.tmatrix * self.smatrix)
                cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                           self.eorder, self.nodesfirst)
                cr.restore()

            elif (isinstance(self.picked, Edge) or
                    (isinstance(self.picked, PropertyMap) and self.picked.key_type() == 'e')):
                # draw edges connected selected vertices
                # no vertices
                vprops = self.vprops.copy()
                vprops["color"] = (0., 0., 0., 0.)
                vprops["fill_color"] = (0., 0., 0., 0.)
                vprops["text_color"] = (0., 0., 0., 0.)
                eprops = self.eprops.copy()
                eprops["color"] = (0.9372549019607843, 0.1607843137254902, 0.1607843137254902, .9)
                eprops["seamless"] = True

                if self.highlight_color is not None:
                    eprops["color"] = self.highlight_color

                shown_vertices = self.selected_vertices.copy()
                shown_edges = self.g.new_edge_property("bool", np.logical_not(self.selected_edges.fa))

                infect_vertex_property(GraphView(self.g, directed=False),
                                       shown_vertices, [True])

                u = GraphView(self.g,
                              vfilt=self.g.new_vertex_property("bool", np.logical_xor(self.selected_vertices.fa,
                                                                                      shown_vertices.fa)))

                for edge in u.edges():
                    shown_edges[edge] = False

                u = GraphView(self.g, vfilt=shown_vertices, efilt=shown_edges)

                eprops["pen_width"] = self.eprops.get("pen_width",
                                                      _edefaults["pen_width"])
                if isinstance(eprops["pen_width"], PropertyMap):
                    pw = eprops["pen_width"]
                    pw = u.own_property(pw.copy())
                    pw.fa *= 1.1
                else:
                    eprops["pen_width"] *= 1.1

                cr.save()
                cr.set_matrix(self.tmatrix * self.smatrix)
                cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                           self.eorder, self.nodesfirst)
                cr.restore()

                # draw selected edges
                # fake edge halo
                eprops["color"] = (0., 0., 1., 0.5)
                eprops["pen_width"] = 0.4 * size

                if self.preselected_edges is not None:
                    shown_edges = self.g.new_edge_property("bool", np.logical_xor(self.preselected_edges.fa,
                                                                                  self.selected_edges.fa))
                else:
                    shown_edges = self.selected_edges.copy()

                if isinstance(self.prepicked, Edge):
                    shown_edges[self.prepicked] = False

                u = GraphView(self.g, vfilt=shown_vertices, efilt=shown_edges)

                cr.save()
                cr.set_matrix(self.tmatrix * self.smatrix)
                cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                           self.eorder, self.nodesfirst)
                cr.restore()

                if self.preselected_edges is not None:
                    # draw preselected edges
                    # fake edge halo
                    eprops["color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.5)
                    eprops["pen_width"] = 0.4 * size

                    if self.prehighlight_color is not None:
                        eprops["color"] = self.prehighlight_color

                    shown_edges = self.preselected_edges.copy()
                    if isinstance(self.prepicked, Edge):
                        shown_edges[self.prepicked] = False

                    u = GraphView(self.g, efilt=shown_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                if isinstance(self.prepicked, Edge):
                    # draw prepicked edge
                    # fake edge halo
                    eprops = self.eprops.copy()
                    eprops["color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.75)
                    eprops["pen_width"] = 0.4 * size
                    eprops["seamless"] = True

                    shown_edges = self.g.new_edge_property("bool", False)
                    shown_edges[self.prepicked] = True

                    u = GraphView(self.g, efilt=shown_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                # no edges
                eprops = {}
                if isinstance(self.prepicked, Vertex):
                    # draw prepicked vertices
                    vprops = self.vprops.copy()
                    vprops["halo"] = True
                    vprops["halo_color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.75)

                    shown_vertices = self.g.new_vertex_property("bool", False)
                    shown_vertices[self.prepicked] = True

                    u = GraphView(self.g, vfilt=shown_vertices, efilt=self.__no_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, self.eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                if self.preselected_vertices is not None:
                    # draw preselected vertices
                    vprops = self.vprops.copy()
                    vprops["halo"] = True
                    vprops["halo_color"] = (1., 0.7647058823529411, 0.13725490196078433, 0.5)

                    if self.prehighlight_color is not None:
                        vprops["halo_color"] = self.prehighlight_color

                    shown_vertices = self.preselected_vertices.copy()
                    if isinstance(self.prepicked, Vertex):
                        shown_vertices[self.prepicked] = False

                    u = GraphView(self.g, vfilt=shown_vertices, efilt=self.__no_edges)

                    cr.save()
                    cr.set_matrix(self.tmatrix * self.smatrix)
                    cairo_draw(u, self.pos, cr, vprops, self.eprops, self.vorder,
                               self.eorder, self.nodesfirst)
                    cr.restore()

                    self.highlight.fa = np.logical_xor(self.selected_vertices.fa,
                                                       self.preselected_vertices.fa)
                else:
                    self.highlight.fa = self.selected_vertices.fa

                # draw selected vertices and connected edges
                vprops = self.vprops.copy()
                vprops["halo"] = self.highlight
                vprops["halo_color"] = (0.9372549019607843, 0.1607843137254902, 0.1607843137254902, .9)
                vprops["halo_size"] = 1.3

                if self.highlight_color is not None:
                    vprops["halo_color"] = self.highlight_color

                shown_vertices = self.selected_vertices.copy()

                if isinstance(self.prepicked, Vertex):
                    shown_vertices[self.prepicked] = False

                u = GraphView(self.g, vfilt=shown_vertices, efilt=self.__no_edges)

                cr.save()
                cr.set_matrix(self.tmatrix * self.smatrix)
                cairo_draw(u, self.pos, cr, vprops, eprops, self.vorder,
                           self.eorder, self.nodesfirst)
                cr.restore()

        if self.srect is not None:
            cr.move_to(self.srect[0], self.srect[1])
            cr.line_to(self.srect[0], self.srect[3])
            cr.line_to(self.srect[2], self.srect[3])
            cr.line_to(self.srect[2], self.srect[1])
            cr.line_to(self.srect[0], self.srect[1])
            cr.close_path()
            cr.set_source_rgba(0, 0, 1, 0.3)
            cr.fill()

        if self.zrect is not None:
            cr.move_to(self.zrect[0], self.zrect[1])
            cr.line_to(self.zrect[0], self.zrect[3])
            cr.line_to(self.zrect[2], self.zrect[3])
            cr.line_to(self.zrect[2], self.zrect[1])
            cr.line_to(self.zrect[0], self.zrect[1])
            cr.close_path()
            cr.set_source_rgba(0, 0, 1, 0.3)
            cr.fill()

        if self.new_edge is not None:
            vprops = {"color": (0, 0, 0, 0), "fill_color": (0, 0, 0, 0)}
            eprops = {prop: self.eprops[prop] for prop in
                      ["color", "pen_width",
                       "start_marker", "mid_marker", "end_marker", "marker_size", "mid_marker_pos",
                       "gradient", "dash_style", "sloppy", "seamless"]
                      if prop in self.eprops}

            g = Graph()
            s, t = g.add_vertex(2)
            g.add_edge(s, t)
            epos = g.new_vertex_property("vector<double>")
            epos[s] = self.pos[self.new_edge[0]]
            epos[t] = self.new_edge[1]

            cr.save()
            cr.set_matrix(self.tmatrix * self.smatrix)
            cairo_draw(g, epos, cr, vprops, eprops, self.vorder,
                       self.eorder, self.nodesfirst)
            cr.restore()

        if self.regenerate_offset > 0:
            icon = self.render_icon(Gtk.STOCK_EXECUTE, Gtk.IconSize.BUTTON)
            Gdk.cairo_set_source_pixbuf(cr, icon, 10, 10)
            cr.paint()

        # deleted code: show picked vertex index according to display_props in lower left corner

        if self.regenerate_offset > 0:
            self.queue_draw()
        return False

    def pos_to_device(self, pos, dist=False, surface=False, cr=None):
        r"""Convert a position from the graph space to the widget space."""
        ox, oy = self.get_window().get_position()
        if cr is None:
            cr = self.get_window().cairo_create()
            if surface:
                cr.set_matrix(self.smatrix)
            else:
                cr.set_matrix(self.tmatrix * self.smatrix)
        if dist:
            return cr.user_to_device_distance(pos[0], pos[1])
        else:
            x, y = cr.user_to_device(pos[0], pos[1])
            return x - ox, y - oy

    def pos_from_device(self, pos, dist=False, surface=False, cr=None):
        r"""Convert a position from the widget space to the device space."""
        ox, oy = self.get_window().get_position()
        if cr is None:
            cr = self.get_window().cairo_create()
            if surface:
                cr.set_matrix(self.smatrix)
            else:
                cr.set_matrix(self.tmatrix * self.smatrix)
        if dist:
            return cr.device_to_user_distance(pos[0], pos[1])
        else:
            return cr.device_to_user(pos[0] + ox, pos[1] + oy)

    def init_vertex_matrix(self):
        r"""Init vertex matrix."""
        if self.g.num_vertices() == 1:
            self.vertex_matrix = None
        else:
            pos_x, pos_y = ungroup_vector_property(self.pos, [0, 1])
            x_range = [pos_x.fa.min(), pos_x.fa.max()]
            y_range = [pos_y.fa.min(), pos_y.fa.max()]
            m_res = min(x_range[1] - x_range[0],
                        y_range[1] - y_range[0]) / np.sqrt(self.g.num_vertices())
            if m_res == 0:
                self.pos = sfdp_layout(self.g)
            self.vertex_matrix = VertexMatrix(self.g, self.pos)

    # IDEA: a feature VertexMatrix is severely lacking
    def is_hit(self, pos):
        if self.g.num_vertices() == 0:
            return None

        def wrap_prop(prop):
            def mapped_prop(item):
                return prop[item]

            def single_prop(item):
                return prop

            return mapped_prop if isinstance(prop, PropertyMap) else single_prop

        size = wrap_prop(self.vprops["size"])
        pos = np.array(pos)

        if self.g.num_vertices() == 1:
            v = next(self.g.vertices())
            ndist = ((pos - self.pos[v].a[:2]) ** 2).sum()
            if ndist * 3 < (size(v) / self.scale) ** 2:
                return v
        else:
            if self.vertex_matrix is None:
                self.init_vertex_matrix()

            box = self.vertex_matrix.get_box(pos)

            for i in range(-1, 2):
                for j in range(-1, 2):
                    b = (box[0] + i, box[1] + j)
                    for v in self.vertex_matrix.m[b]:
                        ndist = ((pos - self.pos[v].a[:2]) ** 2).sum()
                        if ndist * 3 < (size(v) / self.scale) ** 2:
                            return v
        return None

    def fit_to_window(self, ink=False, g=None):
        r"""Fit graph to window."""
        geometry = [self.get_allocated_width(), self.get_allocated_height()]
        ox, oy = self.get_window().get_position()
        if g is None:
            g = self.g
        pos = g.own_property(self.pos)
        cr = self.get_window().cairo_create()
        offset, zoom = fit_to_view(g, pos, geometry,
                                   self.vprops.get("size", 0),
                                   self.vprops.get("pen_width", 0),
                                   self.tmatrix * self.smatrix,
                                   self.vprops.get("text", None),
                                   self.vprops.get("font_family",
                                                   _vdefaults["font_family"]),
                                   self.vprops.get("font_size",
                                                   _vdefaults["font_size"]),
                                   self.pad,
                                   cr)
        self.scale *= zoom
        m = cairo.Matrix()
        m.translate(offset[0] + ox, offset[1] + oy)
        m.scale(zoom, zoom)
        self.tmatrix = self.tmatrix * self.smatrix * m
        self.smatrix = cairo.Matrix()
        if ink:
            scale_ink(zoom, self.vprops, self.eprops)

    def position_parallel_edges(self):
        r"""Calculate control points for parallel edges."""
        # if "control_points" not in self.eprops:
        #     self.eprops["control_points"] = self.g.new_edge_property("vector<double>")
        distance = self.vprops.get("size", _vdefaults["size"])
        if isinstance(distance, PropertyMap):
            distance = distance.fa.mean()
        distance /= 1.5 * self.scale
        self.eprops["control_points"] = position_parallel_edges(self.g, self.pos, np.nan, distance)

    def do_graph_changed(self, to):
        r"""Regenerates surface and redraws widget if ``to`` is ``True``. Stores value of ``to`` for later.
        (see :meth:`~GraphEditorWidget.is_changed`)."""
        self._changed = to
        if to:
            self.position_parallel_edges()
            self.regenerate_surface(reset=True, complete=True)
            self.queue_draw()

    def do_picked_changed(self):
        r"""Redraws widget after updating
        :attr:`~GraphEditorWidget.selected_vertices` vertex :class:`~graph_tool.PropertyMap` and
        :attr:`~GraphEditorWidget.selected_edges` edge :class:`~graph_tool.PropertyMap`."""
        if self.picked is not None:
            if (isinstance(self.picked, Vertex) or
                    (isinstance(self.picked, PropertyMap) and self.picked.key_type() == 'v')):

                hsrc = edge_endpoint_property(self.g, self.selected_vertices, "source")
                htgt = edge_endpoint_property(self.g, self.selected_vertices, "target")
                self.selected_edges.fa = np.logical_or(hsrc.fa, htgt.fa)

            elif (isinstance(self.picked, Edge) or
                  (isinstance(self.picked, PropertyMap) and self.picked.key_type() == 'e')):
                u = GraphView(self.g,
                              efilt=self.selected_edges)

                # IDEA: do it with libcore
                # like edge_endpoint_property, but has input as an edge property
                self.selected_vertices.fa = False
                for edge in u.edges():
                    self.selected_vertices[edge.source()] = True
                    self.selected_vertices[edge.target()] = True

            if self.preselected_vertices is not None:
                self.preselected_vertices.fa = np.logical_and(self.selected_vertices.fa,
                                                              self.preselected_vertices.fa)
            if self.preselected_edges is not None:
                self.preselected_edges.fa = np.logical_and(self.selected_edges.fa,
                                                           self.preselected_edges.fa)
        else:
            self.selected_vertices.fa = False
            self.selected_edges.fa = False
            self.preselected_vertices = None
            self.preselected_edges = None
        self.queue_draw()

    def button_press_event(self, widget, event):
        r"""Handle button press."""

        if self.g.num_vertices() == 0 and self.edit_mode != GraphEditorWidget.modes.place_node:
            return

        if self.is_zooming or self.is_rotating or self.is_drag_gesture:
            return

        state = event.state
        self.pointer = [event.x, event.y]

        if event.button == 1 and not state & Gdk.ModifierType.CONTROL_MASK:
            if state & Gdk.ModifierType.SHIFT_MASK:
                hit = self.is_hit(self.pos_from_device(self.pointer))
                # shift select
                if hit is not None:
                    if (self.picked is not None and (isinstance(self.picked, Edge) or
                                                     (isinstance(self.picked, PropertyMap) and
                                                      self.picked.key_type() == 'e'))):
                        self.selected_vertices.fa = False
                    value = self.selected_vertices[hit]
                    if value and self.preselected_vertices is not None:
                        self.preselected_vertices[hit] = False
                    self.selected_vertices[hit] = not value
                    if self.selected_vertices.fa.sum() > 1:
                        self.picked = self.selected_vertices
                    else:
                        self.picked = next((v for v in self.g.vertices() if self.selected_vertices[v]), None)
                    self.emit("picked-changed")
                self.srect = 2 * self.pointer
            else:
                if self.edit_mode == GraphEditorWidget.modes.place_node:
                    # place node
                    hit = self.g.add_vertex(1)
                    self.pos[hit] = self.pos_from_device(self.pointer)
                    if self.vertex_matrix is not None:
                        self.vertex_matrix.add_vertex(hit)
                    geometry = (self.get_allocated_width(),
                                self.get_allocated_height())
                    adjust_default_sizes(self.g, geometry, self.vprops, self.eprops, force=True)
                    self.emit("graph-changed", True)
                else:
                    hit = self.is_hit(self.pos_from_device(self.pointer))
                if hit is not None:
                    if self.edit_mode == GraphEditorWidget.modes.place_edge:
                        # place edge
                        self.new_edge = [hit, self.pos_from_device(self.pointer)]
                    else:
                        # move
                        if (self.picked is None or (isinstance(self.picked, Edge) or
                            (isinstance(self.picked, PropertyMap) and self.picked.key_type() == 'e')) or
                                not self.selected_vertices[hit]):
                            self.selected_vertices.fa = False
                            self.selected_vertices[hit] = True
                            self.picked = hit
                            self.preselected_vertices = None
                            self.emit("picked-changed")
                        self.drag_vector = self.pointer
                        u = GraphView(self.g, vfilt=self.selected_vertices)
                        saved_pos = u.own_property(self.pos).copy()
                        self.is_moving = (u, saved_pos, self.edit_mode == GraphEditorWidget.modes.place_node)
                        self.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.FLEUR))
                else:
                    # pan
                    self.drag_vector = self.pointer
                    self.is_panning = True
                    self.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.HAND2))
        elif event.button == 1 and state & Gdk.ModifierType.CONTROL_MASK:
            # ctrl zoom
            self.zrect = 2 * self.pointer
        elif event.button == 3:
            # whatever, never mind
            if self.is_moving is not None:
                self.drag_vector = None
                u, saved_pos, is_new = self.is_moving
                if not is_new:
                    for v in u.vertices():
                        self.vertex_matrix.update_vertex(self.g.vertex(int(v)),
                                                         saved_pos[v])
                else:
                    for v in u.vertices():
                        self.g.remove_vertex(v)
                    self.init_vertex_matrix()
                    self.emit("graph-changed", True)
                self.is_moving = None
                self.moved_picked = False
                self.picked = None
                self.emit("picked-changed")
            if self.srect is not None:
                self.srect = None
                self.queue_draw()
            elif self.zrect is not None:
                self.zrect = None
                self.queue_draw()
            elif self.new_edge is not None:
                self.new_edge = None
                self.queue_draw()
            else:
                self.picked = None
                self.preselected_vertices = None
                self.emit("picked-changed")
                self.selected_vertices.fa = False

    def button_release_event(self, widget, event):
        r"""Handle button release."""

        if self.g.num_vertices() == 0:
            return

        if self.is_zooming or self.is_rotating or self.is_drag_gesture:
            return

        if event.button == 1:
            if self.zrect is not None:
                # get centered
                geometry = [self.get_allocated_width(),
                            self.get_allocated_height()]
                dx = abs(self.zrect[2] - self.zrect[0])
                dy = abs(self.zrect[3] - self.zrect[1])

                zoom_x = geometry[0] / dx if dx != 0 else 1
                zoom_y = geometry[1] / dy if dy != 0 else 1
                zoom = min(zoom_x, zoom_y)

                center = ((self.zrect[0] + self.zrect[2]) / 2, (self.zrect[1] + self.zrect[3]) / 2)
                cpos = self.pos_from_device(center)

                self.scale *= zoom
                m = cairo.Matrix()
                m.scale(zoom, zoom)
                self.tmatrix = self.tmatrix.multiply(m)

                target = (geometry[0] / 2, geometry[1] / 2)
                tpos = self.pos_from_device(target)

                self.tmatrix.translate(tpos[0] - cpos[0] * (1 + 1 / self.scale),
                                       tpos[1] - cpos[1] * (1 + 1 / self.scale))

                self.position_parallel_edges()
                self.lazy_regenerate = True
                self.zrect = None
            elif self.srect is not None:
                if (self.picked is not None and (isinstance(self.picked, Edge) or
                                                 (isinstance(self.picked, PropertyMap) and
                                                  self.picked.key_type() == 'e'))):
                    self.selected_vertices.fa = False
                p1 = [self.srect[0], self.srect[1]]
                p2 = [self.srect[2], self.srect[3]]
                poly = [p1, [p1[0], p2[1]], p2, [p2[0], p1[1]]]
                poly = [self.pos_from_device(x) for x in poly]

                before = self.selected_vertices.fa.sum()
                self.vertex_matrix.mark_polygon(poly, self.selected_vertices)
                after = self.selected_vertices.fa.sum()
                if after > 1:
                    self.picked = self.selected_vertices
                else:
                    self.picked = next((v for v in self.g.vertices() if self.selected_vertices[v]), None)
                if before != after:
                    self.emit("picked-changed")
                self.srect = None
            elif self.new_edge is not None:
                hit = self.is_hit(self.pos_from_device((event.x, event.y)))
                if hit is not None:
                    self.g.add_edge(self.new_edge[0], hit)
                self.emit("graph-changed", True)
                self.new_edge = None
            elif self.moved_picked:
                self.drag_vector = None
                self.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.ARROW))
                self.moved_picked = False
                self.emit("graph-changed", True)
            else:
                self.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.ARROW))

            self.queue_draw()
            self.is_moving = None
            self.is_panning = False

    def motion_notify_event(self, widget, event):
        r"""Handle pointer motion."""

        if self.is_zooming or self.is_rotating:
            return

        if event.is_hint:
            x, y, state = event.window.get_pointer()[1:]
        else:
            x = event.x
            y = event.y
            state = event.state

        self.pointer = [x, y]

        if state & Gdk.ModifierType.BUTTON1_MASK:
            if state & Gdk.ModifierType.CONTROL_MASK and self.zrect is not None:
                self.zrect[2:] = self.pointer
            elif state & Gdk.ModifierType.SHIFT_MASK and self.srect is not None:
                self.srect[2:] = self.pointer
            elif self.new_edge is not None:
                self.new_edge[1] = self.pos_from_device(self.pointer)
            elif (self.is_moving is not None and self.picked is not None and
                    self.drag_vector != self.pointer):
                p = self.pos_from_device(self.pointer)
                if isinstance(self.picked, PropertyMap) and self.picked.key_type() == 'v':
                    c = self.pos_from_device(self.drag_vector)
                    u = GraphView(self.g, vfilt=self.selected_vertices)
                    delta = np.asarray(p) - np.asarray(c)
                    for v in u.vertices():
                        new_pos = self.pos[v].a + delta
                        self.vertex_matrix.update_vertex(self.g.vertex(int(v)),
                                                         new_pos)
                elif isinstance(self.picked, Vertex):
                    if self.vertex_matrix is not None:
                        self.vertex_matrix.update_vertex(self.picked, p)
                    else:
                        self.pos[self.picked] = p
                self.drag_vector = self.pointer
                self.moved_picked = True
            elif self.is_panning:
                offset = [x - self.drag_vector[0],
                          y - self.drag_vector[1]]
                m = cairo.Matrix()
                m.translate(offset[0], offset[1])
                self.smatrix = self.smatrix * m
                self.drag_vector = self.pointer
            self.queue_draw()

    def scroll_event(self, widget, event):
        r"""Handle scrolling."""

        if self.is_zooming or self.is_rotating:
            return

        self.pointer = (event.x, event.y)
        state = event.state
        zoom = 1.

        if event.direction == Gdk.ScrollDirection.SMOOTH:
            is_smooth, dx, dy = event.get_scroll_deltas()
            if dy == 0:
                return
        else:
            dy = 1

        if state & Gdk.ModifierType.CONTROL_MASK:
            if (event.direction == Gdk.ScrollDirection.UP or
                    event.direction == Gdk.ScrollDirection.SMOOTH):
                if dy > 0:
                    zoom = 1. + (1. / .9 - 1) * abs(dy)
                else:
                    zoom = 1. / (1. + abs(dy) / 9)
            elif event.direction == Gdk.ScrollDirection.DOWN:
                zoom = .9

            if zoom != 1:
                # keep centered
                center = self.pointer
                cpos = self.pos_from_device(center)

                self.scale *= zoom
                m = cairo.Matrix()
                m.scale(zoom, zoom)
                self.tmatrix = self.tmatrix.multiply(m)

                ncpos = self.pos_from_device(center)
                self.tmatrix.translate(ncpos[0] - cpos[0],
                                       ncpos[1] - cpos[1])

                self.position_parallel_edges()
                self.lazy_regenerate = True
        elif state & Gdk.ModifierType.SHIFT_MASK:
            # pan x
            m = cairo.Matrix()
            m.translate(dy * -10, 0)  # sensitivity
            self.smatrix = self.smatrix * m
        else:
            hit = self.is_hit(self.pos_from_device(self.pointer))
            if (hit is not None and self.picked is not None and
                    (self.highlight[hit] or self.selected_vertices[hit])):
                    # HACK: due to self-loops all_edges != out_edges + in_edges
                    hit_edge_pool = list(hit.out_edges())
                    hit_edge_pool += [edge for edge in hit.in_edges() if edge not in hit_edge_pool]
                    if len(hit_edge_pool) > 0:
                        if self.picked in hit_edge_pool:
                            i = hit_edge_pool.index(self.picked)
                            i += 1 if dy > 0 else -1
                            i += len(hit_edge_pool)
                            i %= len(hit_edge_pool)
                        else:
                            i = 0 if dy > 0 else -1
                        selected_edge = hit_edge_pool[i]

                        self.selected_vertices.fa = False
                        self.selected_edges.fa = False
                        self.selected_edges[selected_edge] = True
                        self.preselected_vertices = None
                        self.picked = selected_edge
                        self.emit("picked-changed")
            else:
                # pan y
                m = cairo.Matrix()
                m.translate(0, dy * -10)  # sensitivity
                self.smatrix = self.smatrix * m

        self.queue_draw()

    def key_press_event(self, widget, event):
        r"""Handle key press."""

        if self.is_zooming or self.is_rotating:
            return

        if event.keyval == ord('z'):
            u = GraphView(self.g, vfilt=self.selected_vertices)
            self.fit_to_window(g=u)
            self.position_parallel_edges()
            self.regenerate_surface(reset=True)
        if self.srect is not None:
            if event.keyval == 65505 or event.keyval == 65506:  # Shift
                self.srect[2:] = self.pointer
        elif not self.is_moving and (event.keyval == 65507 or event.keyval == 65508):  # Ctrl
            if self.zrect is not None:
                self.zrect[2:] = self.pointer
            cursor = Gtk.Widget.render_icon(Gtk.Image(), Gtk.STOCK_ZOOM_IN, Gtk.IconSize.BUTTON)
            self.get_window().set_cursor(Gdk.Cursor.new_from_pixbuf(self.get_display(), cursor, 0, 0))

        self.queue_draw()

    def key_release_event(self, widget, event):
        r"""Handle release event."""

        if self.is_zooming or self.is_rotating:
            return

        if not self.is_moving and (event.keyval == 65507 or event.keyval == 65508):  # Ctrl
            self.get_window().set_cursor(Gdk.Cursor(Gdk.CursorType.ARROW))

    # Touch gestures

    def zoom_begin(self, gesture, seq):
        self.is_zooming = True
        self.zoom_scale = 1.

    def zoom_end(self, gesture, seq):
        self.is_zooming = False
        self.regenerate_surface(reset=True)
        self.queue_draw()

    def scale_changed(self, gesture, scale):
        zoom = scale / self.zoom_scale
        self.zoom_scale = scale
        center = gesture.get_bounding_box_center()[1:]
        cpos = self.pos_from_device(center, surface=True)
        self.smatrix.scale(zoom, zoom)
        ncpos = self.pos_from_device(center, surface=True)
        self.smatrix.translate(ncpos[0] - cpos[0],
                               ncpos[1] - cpos[1])
        scale_ink(zoom, self.vprops, self.eprops)
        self.queue_draw()

    def rotate_begin(self, gesture, seq):
        self.is_rotating = True
        self.angle = None

    def rotate_end(self, gesture, seq):
        self.is_rotating = False

    def angle_changed(self, gesture, angle, angle_delta):
        if self.angle is None:
            self.angle = angle
        delta = angle - self.angle
        self.angle = angle
        center = gesture.get_bounding_box_center()[1:]
        m = cairo.Matrix()
        m.translate(center[0], center[1])
        m.rotate(delta)
        m.translate(-center[0], -center[1])
        self.smatrix = self.smatrix.multiply(m)
        self.queue_draw()

    def drag_gesture_begin(self, gesture, seq):
        self.drag_last = [0, 0]
        self.is_drag_gesture = True
        self.selected_vertices.fa = False
        self.preselected_vertices = None
        self.picked = False
        self.emit("picked-changed")

    def drag_gesture_end(self, gesture, seq):
        self.is_drag_gesture = False

    def drag_gesture_update(self, gesture, dx, dy):
        delta = (dx - self.drag_last[0], dy - self.drag_last[1])
        self.drag_last = (dx, dy)
        m = cairo.Matrix()
        m.translate(delta[0], delta[1])
        self.smatrix = self.smatrix.multiply(m)
        self.queue_draw()

    # Graph manipulations

    def merge_parallel_edges(self, label_sep=', '):
        r"""Removes parallel edges only keeps a singular one and
        joins the labels of them separated by ``label_sep``."""
        marked = label_parallel_edges(self.g, mark_only=True)

        if "text" in self.eprops:
            for edge in self.g.edges():
                if marked[edge]:
                    # supposed remaining won't get marked
                    remaining = self.g.edge(edge.source(), edge.target())
                    if self.eprops["text"][edge]:
                        if self.eprops["text"][remaining]:
                            self.eprops["text"][remaining] += label_sep + self.eprops["text"][edge]
                        else:
                            self.eprops["text"][remaining] = self.eprops["text"][edge]

        remove_labeled_edges(self.g, marked)


# HACK: several changes
# take font_size in account,
# adjust eprops pen_width and marker_size even if vprops has pen_width and not force
def adjust_default_sizes(g, geometry, vprops, eprops, force=False):
    if "size" not in vprops or force:
        area = geometry[0] * geometry[1]
        n = max(g.num_vertices(), 1)
        size = np.sqrt(area / n) / 3.5
        if "text" in vprops:
            font_size = vprops.get("font_size", _vdefaults["font_size"])
            size = max(size, font_size if n == 1 else font_size * np.log10(n))
        vprops["size"] = size
    elif isinstance(vprops["size"], PropertyMap):
        size = vprops["size"].fa.mean()
    else:
        size = vprops["size"]

    if "pen_width" not in vprops or force:
        vprops["pen_width"] = size / 10

    if "pen_width" not in eprops or force:
        eprops["pen_width"] = size / 10
    if "marker_size" not in eprops or force:
        eprops["marker_size"] = size * 0.6
