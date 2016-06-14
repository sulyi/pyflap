#!/usr/bin/env python3

from gtk_editor.gtk_editor import *

# testing


def create_random_graph():
    g = Graph()
    vprops_labels = g.new_vertex_property("string")
    g.add_vertex(100)

    for i, node in enumerate(g.vertices()):
        vprops_labels[node] = str(i)
    g.vertex_properties["text"] = vprops_labels

    # insert some random links
    for s, t in zip(np.random.randint(0, 100, 100), np.random.randint(0, 100, 100)):
        g.add_edge(g.vertex(s), g.vertex(t))

    pos = sfdp_layout(g)

    return g, pos


def create_my_graph():
    g = Graph()
    vprops_labels = g.new_vertex_property("string")
    g.add_vertex(5)

    for i, node in enumerate(g.vertices()):
        vprops_labels[node] = str(i)
    g.vertex_properties["text"] = vprops_labels

    g.add_edge(0, 1)
    g.add_edge(1, 2)
    g.add_edge(2, 2)
    g.add_edge(2, 2)
    g.add_edge(2, 1)
    g.add_edge(3, 2)
    g.add_edge(3, 2)
    g.add_edge(3, 1)
    g.add_edge(2, 3)
    g.add_edge(4, 2)

    pos = sfdp_layout(g)

    return g, pos


def add_some_graphs(target):
    g, pos = create_random_graph()
    target.add_new_tab(g, pos)

    g, pos = create_random_graph()
    target.add_new_tab(g, pos, "test_1.gml")
    target.get_current_tab().emit("graph-changed", True)

    g = Graph()
    v1, v2 = g.add_vertex(2)
    pos = g.new_vertex_property("vector<double>")
    pos[v1] = (10, 11)
    target.add_new_tab(g, pos)

    g, pos = create_my_graph()
    target.add_new_tab(g, pos, "test_my.gml")
    target.get_current_tab().emit("graph-changed", True)


default_geometry = (800, 600)
_window_list = []
window_title = "pyflap editor"


def main():
    win = GraphEditorWindow(geometry=default_geometry, title=window_title)
    _window_list.append(win)

    def destroy_callback(window, event):

        global _window_list
        # return all(w.destroy() for w in _window_list)
        # cancels event at first hiccup
        all_destroyed = True
        for w in _window_list:
            if w.destroy():
                all_destroyed = False
        return not all_destroyed

    def first_callback():
        add_some_graphs(win)
        return False

    win.connect("destroy", Gtk.main_quit)
    win.connect("delete-event", destroy_callback)
    win.show_all()
    gobject.idle_add(first_callback)

    Gtk.main()

if __name__ == '__main__':
    main()
