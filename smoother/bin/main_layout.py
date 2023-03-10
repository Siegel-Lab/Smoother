__author__ = "Markus Schmidt"
__version__ = "0.0.3"
__email__ = "Markus.Schmidt@lmu.de"

from bokeh.layouts import grid, row, column
from bokeh.plotting import figure, curdoc
from bokeh.models.tools import ToolbarBox, ProxyToolbar
from bokeh.models import ColumnDataSource, Dropdown, Button, RangeSlider, Slider, TextInput, FuncTickFormatter, Div, HoverTool, Toggle, Box, Spinner, MultiSelect, CheckboxGroup, CrosshairTool, ColorPicker, ImageURLTexture, TextAreaInput, AllLabels, Paragraph, BasicTickFormatter
#from bin.unsorted_multi_choice import UnsortedMultiChoice as MultiChoice
from bokeh.io import export_png, export_svg
import math
import time
from datetime import datetime
from tornado import gen
from bokeh.document import without_document_lock
from bokeh.models import Panel, Tabs, Spacer, Slope, PreText, CustomJS, FixedTicker
from bokeh.models import Range1d, ColorBar, LinearColorMapper
import os
import sys
#from bin.heatmap_as_r_tree import *
from bokeh.palettes import Viridis256, Colorblind, Plasma256, Turbo256
from datetime import datetime, timedelta
import psutil
from concurrent.futures import ThreadPoolExecutor
from bokeh.models import BoxAnnotation
from bokeh.models.tickers import AdaptiveTicker
from libsmoother import Quarry
import json
import shutil
from bin.figure_maker import FigureMaker, DROPDOWN_HEIGHT, FONT
from bin.extra_ticks_ticker import *
from bin.export_tsv import export_tsv
from bokeh import events
import bin.global_variables
import site
from pathlib import Path

SETTINGS_WIDTH = 400
BUTTON_HEIGHT = 30
DEFAULT_SIZE = 50
ANNOTATION_PLOT_NAME = "Annotation panel"
RAW_PLOT_NAME = "Secondary data panel"

DIV_MARGIN = (5, 5, 0, 5)
BTN_MARGIN = (3, 3, 3, 3)
BTN_MARGIN_2 = (3, 3, 3, 3)

CONFIG_FILE_VERSION = 0.1

DEFAULT_TEXT_INPUT_HEIGHT = 30

executor = ThreadPoolExecutor(max_workers=1)

SMOOTHER_PATH = os.fspath(Path(os.path.join(site.getsitepackages()[0], "smoother")).resolve())


## @todo use multi-inheritance to split this class into smaller ones


class MainLayout:
    def dropdown_select_h(self, title, event, tooltip):
        ret = Dropdown(label=title, menu=[], width=SETTINGS_WIDTH, sizing_mode="fixed", 
                        css_classes=["other_button", "tooltip", tooltip], height=DROPDOWN_HEIGHT)

        options = []
        d = {}

        def make_menu():
            menu = []
            for name, key in options:
                menu.append((("??? " if d[key] else "??? ") + name, key))
            ret.menu = menu

        def set_menu(op, active_item=None):
            nonlocal options
            nonlocal d
            options = op
            d = {}
            for _, key in options:
                d[key] = key == active_item
            if active_item is None:
                d[options[0][1]] = True
            make_menu()
            if not active_item is None:
                event(active_item)

        def _event(e):
            for _, key in options:
                d[key] = False
            d[e.item] = True
            event(e.item)
            make_menu()
        ret.on_click(_event)
        return ret, set_menu

    def dropdown_select(self, title, tooltip, *options, active_item=None, event=None):
        if event is None:
            def default_event(e):
                self.session.set_value(active_item, e)
                self.trigger_render()
            event = default_event
        ret, set_menu = self.dropdown_select_h(title, event, tooltip)
        if not active_item is None:
            self.dropdown_select_config.append((lambda x: set_menu([*options], x), active_item))
        else:
            set_menu(options)
        return ret

    def dropdown_select_session(self, title, tooltip, session_key, active_item, add_keys=[], event=None):
        if event is None:
            def default_event(e):
                self.session.set_value(active_item, e)
                self.trigger_render()
            event = default_event
        ret, set_menu = self.dropdown_select_h(title, event, tooltip)
        def set_menu_2(x):
            set_menu(add_keys + [(x,x) for x in self.session.get_value(session_key)], x)
        self.dropdown_select_config.append((set_menu_2, active_item))
        return ret

    def multi_choice(self, label, tooltip, checkboxes, session_key=None, callback=None, orderable=True):
        if callback is None:
            def default_callback(n, cb):
                for v in cb.values():
                    self.session.set_value(v[0], v[1])
                if not session_key is None:
                    self.session.set_value(session_key, n)
                self.trigger_render()
            callback = default_callback
        div = Div(text=label, align="center")
        SYM_WIDTH = 10
        SYM_CSS = ["other_button"]
        CHECK_WIDTH = 19*len(checkboxes)
        ELEMENTS_PER_PAGE = 10

        #col.max_height=150
        col = column([], sizing_mode="stretch_width")
        empty = Div(text="", sizing_mode="fixed", width=30, height=BUTTON_HEIGHT)
        
        spinner = TextInput(value="1", width=50, height=BUTTON_HEIGHT, sizing_mode="fixed", visible=False)
        next_page = Button(label="", css_classes=SYM_CSS + ["fa_page_next_solid"], width=SYM_WIDTH, 
                            height=SYM_WIDTH, sizing_mode="fixed", button_type="light", visible=False, align="center")
        prev_page = Button(label="", css_classes=SYM_CSS + ["fa_page_previous_solid"], width=SYM_WIDTH, 
                           height=SYM_WIDTH, sizing_mode="fixed", button_type="light", visible=False, align="center")
        page_div = Div(text="Page:", width=30, height=BUTTON_HEIGHT, sizing_mode="fixed", visible=False, align="center")
        layout = column([row([div, Spacer(width_policy="max"), prev_page, page_div, spinner, next_page, empty], sizing_mode="stretch_width"), row([
            Div(text="", sizing_mode="stretch_width"),
            Div(text="<br>".join(y for _, y in checkboxes), css_classes=["vertical"], width_policy="fixed",
                width=CHECK_WIDTH+5),
            empty
        ], sizing_mode="stretch_width"), col], sizing_mode="stretch_width", css_classes=["outlnie_border", "tooltip", tooltip],
        margin=DIV_MARGIN)

        self.reset_options[label] = [col, [], 1, [spinner, next_page, prev_page, page_div]]
        
        def move_element(opt, ele, up):
            idx = None
            for i, (k, v) in enumerate(opt):
                if k == ele:
                    idx = i
                    break
            if not idx is None:
                if up and idx > 0:
                    return opt[:idx-1] + [opt[idx], opt[idx-1]] + opt[idx+1:]
                elif not up and idx + 1 < len(opt):
                    return opt[:idx] + [opt[idx+1], opt[idx]] + opt[idx+2:]
            return opt

        def trigger_callback():
            cb = {}
            for k, n in checkboxes:
                cb[n] = (k, [])
            order = []
            for n, opts in self.reset_options[label][1]:
                order.append(n)
                for opt in opts:
                    cb[checkboxes[opt][1]][1].append(n)
            callback(order, cb)

        def reset_event(e):
            l = []
            pos = self.reset_options[label][2] - 1
            for idx, (n, opts) in list(enumerate(self.reset_options[label][1]))[pos*ELEMENTS_PER_PAGE:(pos+1)*ELEMENTS_PER_PAGE]:
                if orderable:
                    down_button = Button(label="", css_classes=SYM_CSS + ["fa_sort_down_solid"], width=SYM_WIDTH, 
                                        height=SYM_WIDTH, sizing_mode="fixed", tags=[n], button_type="light")
                    def down_event(n):
                        self.reset_options[label][1] = move_element(self.reset_options[label][1], n, False)
                        reset_event(0)
                        trigger_callback()
                    down_button.on_click(lambda _, n=n: down_event(n))

                    up_button = Button(label="", css_classes=SYM_CSS + ["fa_sort_up_solid"], width=SYM_WIDTH, 
                                        height=SYM_WIDTH, sizing_mode="fixed", tags=[n], button_type="light")
                    def up_event(n):
                        self.reset_options[label][1] = move_element(self.reset_options[label][1], n, True)
                        reset_event(0)
                        trigger_callback()
                    up_button.on_click(lambda _, n=n: up_event(n))

                div = Div(text=n, sizing_mode="stretch_width")
                cg = CheckboxGroup(labels=[""]*len(checkboxes), active=opts, inline=True,
                                   width=CHECK_WIDTH, sizing_mode="fixed", height=19)
                def on_change(idx, cg):
                    self.reset_options[label][1][idx][1] = cg.active
                    trigger_callback()
                cg.on_change("active", lambda _1,_2,_3,idx=idx,cg=cg: on_change(idx,cg))

                if orderable:
                    l.append(row([up_button, down_button, div, cg, empty], sizing_mode="stretch_width"))
                else:
                    l.append(row([div, cg, empty], sizing_mode="stretch_width"))

            if len(l) == 0:
                l = [empty]
            self.reset_options[label][0].children = l

        def spinner_event(x, y, z):
            if spinner.value.isdigit() and int(spinner.value) > 0 and int(spinner.value) <= len(self.reset_options[label][1]) // ELEMENTS_PER_PAGE + 1:
                self.reset_options[label][2] = int(spinner.value)
                reset_event(0)
            else:
                spinner.value = str(self.reset_options[label][2])

        spinner.on_change("value", spinner_event)

        
        def next_page_event():
            if self.reset_options[label][2] < len(self.reset_options[label][1]) // ELEMENTS_PER_PAGE + 1:
                self.reset_options[label][2] += 1
                spinner.value = str(self.reset_options[label][2])
                reset_event(0)
        next_page.on_click(lambda _, : next_page_event())
        def prev_page_event():
            if self.reset_options[label][2] > 1:
                self.reset_options[label][2] -= 1
                spinner.value = str(self.reset_options[label][2])
                reset_event(0)
        prev_page.on_click(lambda _, : prev_page_event())

        def set_options(labels, active_dict):
            self.reset_options[label][1] = []
            for x in self.reset_options[label][3]:
                x.visible = len(labels) > ELEMENTS_PER_PAGE
            for jdx, n in enumerate(labels):
                self.reset_options[label][1].append([n, []])
                for idx, cb in enumerate(checkboxes):
                    if n in active_dict[cb[1]]:
                        self.reset_options[label][1][jdx][1].append(idx)
            reset_event(0)
            trigger_callback()

        return set_options, layout
    
    
    def multi_choice_auto(self, label, tooltip, checkboxes, session_key, callback=None, orderable=True):
        set_options, layout = self.multi_choice(label, tooltip, checkboxes, session_key, callback, orderable)
        self.multi_choice_config.append((set_options, session_key, checkboxes))
        return layout

    def config_row(self, file_nr, callback=None, lock_name=False):
        SYM_WIDTH = 10
        SYM_CSS = ["other_button"]
        with open(SMOOTHER_PATH + '/static/conf/' + str(file_nr) + '.json', 'r') as f:
            settings = json.load(f)
        with open(SMOOTHER_PATH + '/static/conf/factory_' + str(file_nr) + '.json', 'r') as f:
            factory_default = json.load(f)

        if CONFIG_FILE_VERSION != settings["smoother_config_file_version"]:
            print("Config file version does not match: expected", CONFIG_FILE_VERSION, 
                  "but got", settings["smoother_config_file_version"])
        
        name = TextInput(value=settings["display_name"], sizing_mode="stretch_width", disabled=lock_name,
                         height=DEFAULT_TEXT_INPUT_HEIGHT)
        apply_button = Button(label="", css_classes=SYM_CSS + ["fa_apply"], width=SYM_WIDTH, 
                            height=SYM_WIDTH, sizing_mode="fixed", button_type="light", align="center")
        save_button = Button(label="", css_classes=SYM_CSS + ["fa_save"], width=SYM_WIDTH, 
                            height=SYM_WIDTH, sizing_mode="fixed", button_type="light", align="center")
        reset_button = Button(label="", 
                        css_classes=SYM_CSS + ["fa_reset"] if settings != factory_default else ["fa_reset_disabled"], 
                            width=SYM_WIDTH, 
                            height=SYM_WIDTH, sizing_mode="fixed", button_type="light", align="center",
                            disabled=settings == factory_default)
        def save_event():
            def dict_diff(a, b):
                r = {}
                for k in a.keys():
                    if isinstance(a[k], dict):
                        d = dict_diff(a[k], b[k])
                        if len(d) > 0:
                            r[k] = d
                    elif k not in b or a[k] != b[k]:
                        r[k] = a[k]
                return r
            print("saving...")
            settings = dict_diff(self.session.get_value(["settings"]), self.settings_default)
            settings["display_name"] = name.value
            settings["smoother_config_file_version"] = CONFIG_FILE_VERSION
            with open(SMOOTHER_PATH + '/static/conf/' + str(file_nr) + '.json', 'w') as f:
                json.dump(settings, f)
            reset_button.disabled = settings == factory_default
            reset_button.css_classes = SYM_CSS + ["fa_reset"] if settings != factory_default else ["fa_reset_disabled"]
            print("saved")
        save_button.on_click(lambda _: save_event())

        def reset_event():
            shutil.copyfile(SMOOTHER_PATH + '/static/conf/factory_' + str(file_nr) + '.json', 
                            SMOOTHER_PATH + '/static/conf/' + str(file_nr) + '.json')
            reset_button.disabled = True
            reset_button.css_classes = SYM_CSS + ["fa_reset_disabled"]
            with open(SMOOTHER_PATH + '/static/conf/' + str(file_nr) + '.json', 'r') as f:
                settings = json.load(f)
            name.value = settings["display_name"]
        reset_button.on_click(lambda _: reset_event())

        def apply_event():
            print("applying...")
            with open(SMOOTHER_PATH + '/static/conf/' + str(file_nr) + '.json', 'r') as f:
                settings = json.load(f)
            def combine_dict(a, b):
                r = {}
                for k in b.keys():
                    if isinstance(b[k], dict) and k in a:
                        r[k] = combine_dict(a[k], b[k])
                    elif isinstance(b[k], dict):
                        r[k] = b[k]
                    elif k in a:
                        r[k] = a[k]
                    else:
                        r[k] = b[k]
                return r
            self.session.set_value(["settings"], combine_dict(settings, self.session.get_value(["settings"])))
            self.curdoc.hold()
            self.do_config()
            self.curdoc.unhold()
            self.trigger_render()
            print("applied")
        apply_button.on_click(lambda _: apply_event())

        return row([name, apply_button, save_button, reset_button], sizing_mode="stretch_width")

    def make_slider_spinner(self, title, tooltip, settings, width=200, 
                            on_change=None, spinner_width=80, sizing_mode="stretch_width"):
        if on_change is None:
            def default_on_change(val):
                self.session.set_value(settings + ["val"], val)
                self.trigger_render()
            on_change = default_on_change
        spinner = Spinner(width=spinner_width)
        slider = Slider(title=title, show_value=False, width=width-spinner_width, sizing_mode=sizing_mode,
                        start=0, end=1, value=0)

        spinner.js_link("value", slider, "value")
        slider.js_link("value", spinner, "value")
        slider.on_change("value_throttled", lambda _x,_y,_z: on_change(slider.value))
        spinner.on_change("value_throttled", lambda _x,_y,_z: on_change(spinner.value))

        self.slider_spinner_config.append((slider, spinner, on_change, settings))

        return row([slider, spinner], width=width, margin=DIV_MARGIN, css_classes=["tooltip", tooltip])

    def make_range_slider_spinner(self, title, tooltip, settings, width=200, 
                            on_change=None, spinner_width=80, sizing_mode="stretch_width"):
        if on_change is None:
            def default_on_change(val):
                self.session.set_value(settings + ["val_min"], val[0])
                self.session.set_value(settings + ["val_max"], val[1])
                self.trigger_render()
            on_change = default_on_change
        slider = RangeSlider(title=title, show_value=False, width=width-spinner_width*2, sizing_mode=sizing_mode,
                        start=0, end=1, value=(0,1))
        spinner_start = Spinner(width=spinner_width)
        spinner_end = Spinner(width=spinner_width)

        spinner_start.js_on_change('value', CustomJS(args=dict(other=slider), 
                                    code="other.value = [this.value, other.value[1]]" ) )
        slider.js_link("value", spinner_start, "value", attr_selector=0)

        spinner_end.js_on_change('value', CustomJS(args=dict(other=slider), 
                                    code="other.value = [other.value[0], this.value]" ) )
        slider.js_link("value", spinner_end, "value", attr_selector=1)

        slider.on_change("value_throttled", lambda _x,_y,_z: on_change(slider.value))
        spinner_end.on_change("value_throttled", lambda _x,_y,_z: on_change(slider.value))
        spinner_start.on_change("value_throttled", lambda _x,_y,_z: on_change(slider.value))

        self.range_slider_spinner_config.append((slider, spinner_start, spinner_end, on_change, settings))

        return row([slider, spinner_start, spinner_end], width=width, margin=DIV_MARGIN, css_classes=["tooltip", tooltip])

    def make_checkbox(self, title, tooltip="", settings=[], on_change=None, width=SETTINGS_WIDTH):
        div = Div(text=title, sizing_mode="stretch_width", width=width-20)
        cg = CheckboxGroup(labels=[""], width=20)
        if on_change is None:
            def default_event(active):
                self.session.set_value(settings, active)
                self.trigger_render()
            on_change = default_event
        cg.on_change("active", lambda _1,_2,_3: on_change(0 in cg.active))

        self.checkbox_config.append((cg, settings))

        return row([div, cg], width=width, margin=DIV_MARGIN, css_classes=["tooltip", tooltip])

    def config_slider_spinner(self):
        for slider, spinner, on_change, session_key in self.slider_spinner_config:
            value = self.session.get_value(session_key + ["val"])
            start = self.session.get_value(session_key + ["min"])
            end = self.session.get_value(session_key + ["max"])
            step = self.session.get_value(session_key + ["step"])
            
            spinner_min = self.session.get_value(session_key + ["spinner_min_restricted"])
            spinner_max = self.session.get_value(session_key + ["spinner_max_restricted"])

            if spinner_min:
                spinner.low = start
            else:
                spinner.low = None
            if spinner_max:
                spinner.high = end
            else:
                spinner.high = None
            spinner.value = value
            spinner.step = step

            slider.start = start
            slider.end = end
            slider.value = value
            slider.step = step

            on_change(value)

    def config_range_slider_spinner(self):
        for slider, spinner_start, spinner_end, on_change, session_key in self.range_slider_spinner_config:
            value_min = self.session.get_value(session_key + ["val_min"])
            value_max = self.session.get_value(session_key + ["val_max"])
            start = self.session.get_value(session_key + ["min"])
            end = self.session.get_value(session_key + ["max"])
            step = self.session.get_value(session_key + ["step"])

            spinner_min = self.session.get_value(session_key + ["spinner_min_restricted"])
            spinner_max = self.session.get_value(session_key + ["spinner_max_restricted"])

            if spinner_min:
                spinner_start.low = start
            else:
                spinner_start.low = None
            if spinner_max:
                spinner_start.high = end
            else:
                spinner_start.high = None
            spinner_start.value = value_min
            spinner_start.step = step

            if spinner_min:
                spinner_end.low = start
            else:
                spinner_end.low = None
            if spinner_max:
                spinner_end.high = end
            else:
                spinner_end.high = None
            spinner_end.value = value_max
            spinner_end.step = step

            slider.start = start
            slider.end = end
            slider.value = [value_min, value_max]
            slider.step = step

            on_change([value_min, value_max])

    def config_dropdown(self):
        for set_menu, session_key in self.dropdown_select_config:
            set_menu(self.session.get_value(session_key))

    def config_checkbox(self):
        for cg, session_key in self.checkbox_config:
            cg.active = [0] if self.session.get_value(session_key) else []

    def config_multi_choice(self):
        for set_options, session_key, checkboxes in self.multi_choice_config:
            ele_list = self.session.get_value(session_key)
            d = {}
            for key, name in checkboxes:
                d[name] = [ele for ele in ele_list if ele in self.session.get_value(key)] 
            set_options(ele_list, d)

    def do_config(self):
        
        def to_idx(x):
            if x <= 0:
                return 0
            power = int(math.log10(x))
            return 9*power+math.ceil(x / 10**power)-1

        min_ = max(to_idx(self.session.get_value(["dividend"])), 
                          self.session.get_value(["settings", "interface", "min_bin_size", "min"]))
        val_ = max(to_idx(self.session.get_value(["dividend"])), 
                          self.session.get_value(["settings", "interface", "min_bin_size", "val"]))

        self.session.set_value(["settings", "interface", "min_bin_size", "min"], min_)
        self.session.set_value(["settings", "interface", "min_bin_size", "val"], val_)

        self.min_max_bin_size.start = self.session.get_value(["settings", "interface", "min_bin_size", "min"])
        self.min_max_bin_size.end = self.session.get_value(["settings", "interface", "min_bin_size", "max"])
        self.min_max_bin_size.value = self.session.get_value(["settings", "interface", "min_bin_size", "val"])
        self.min_max_bin_size.step = self.session.get_value(["settings", "interface", "min_bin_size", "step"])

        self.undo_button.disabled = not self.session.has_undo()
        self.undo_button.css_classes = ["other_button", "fa_page_previous" if self.undo_button.disabled else "fa_page_previous_solid"]
        self.redo_button.disabled = not self.session.has_redo()
        self.redo_button.css_classes = ["other_button", "fa_page_next" if self.redo_button.disabled else "fa_page_next_solid"]

        self.heatmap.x_range.start = self.session.get_value(["area", "x_start"])
        self.heatmap.x_range.end = self.session.get_value(["area", "x_end"])
        self.heatmap.y_range.start = self.session.get_value(["area", "y_start"])
        self.heatmap.y_range.end = self.session.get_value(["area", "y_end"])


        self.config_slider_spinner()
        self.config_range_slider_spinner()
        self.config_dropdown()
        self.config_checkbox()
        self.config_multi_choice()

        self.low_color.color = self.session.get_value(["settings", "interface", "color_low"])
        self.high_color.color = self.session.get_value(["settings", "interface", "color_high"])

        self.config_show_hide(self.session.get_value(["settings", "interface", "show_hide"]))

        self.export_file.value = self.session.get_value(["settings", "export", "prefix"])

        self.set_active_tools_ti.value = ";".join(self.session.get_value(["settings", "active_tools"]))


    def plot_render_area(self, plot):
        return self.render_areas[plot]

    def update_visibility(self):
        for plot, keys in self.hidable_plots:
            visible = True
            for key in keys:
                if not self.show_hide[key]:
                    visible = False
                    break
            if plot.visible != visible:
                plot.visible = visible
        if not self.unhide_button is None:
            if self.unhide_button.visible == self.show_hide["tools"]:
                self.unhide_button.visible = not self.show_hide["tools"]
        cx = "lightgrey" if self.show_hide["contig_borders"] else None
        cx2 = "lightgrey" if self.show_hide["grid_lines"] else None
        cy = "lightgrey" if self.show_hide["contig_borders"] else None
        cy2 = "lightgrey" if self.show_hide["grid_lines"] else None
        self.slope.line_color = "darkgrey" if self.show_hide["indent_line"] else None
        for plot in self.grid_line_plots:
            if plot.xgrid.grid_line_color != cx:
                plot.xgrid.grid_line_color = cx
            if plot.xgrid.minor_grid_line_color != cx2:
                plot.xgrid.minor_grid_line_color = cx2
            if plot.ygrid.grid_line_color != cy:
                plot.ygrid.grid_line_color = cy
            if plot.ygrid.minor_grid_line_color != cy2:
                plot.ygrid.minor_grid_line_color = cy2

    def toggle_hide(self, key):
        self.show_hide[key] = not self.show_hide[key]
        self.update_visibility()

    def is_visible(self, key):
        return self.show_hide[key]

    def make_show_hide_menu(self):
        menu = []
        for name, key in self.names:
            menu.append(
                (("??? " if self.show_hide[key] or key == "tools" else "??? ") + name, key))
        menu.append(
            (("??? " if self.show_hide["grid_lines"] else "??? ") + "Grid Lines", "grid_lines"))
        menu.append(
            (("??? " if self.show_hide["indent_line"] else "??? ") + "Identity Line", "indent_line"))
        menu.append(
            (("??? " if self.show_hide["contig_borders"] else "??? ") + "Contig Borders", "contig_borders"))
        return menu

    def make_show_hide_dropdown(self, session_key, *names):
        for _, key in names:
            if key == "tools":
                self.show_hide[key] = True
            elif key not in self.show_hide:
                self.show_hide[key] = False
        self.names = names

        self.show_hide_dropdown = Dropdown(label="Show/Hide", menu=self.make_show_hide_menu(),
                       width=SETTINGS_WIDTH, sizing_mode="fixed", css_classes=["other_button", "tooltip", "tooltip_show_hide"], height=DROPDOWN_HEIGHT)

        def event(e):
            self.toggle_hide(e.item)
            self.session.set_value(session_key + [e.item], not self.session.get_value(session_key + [e.item]))
            self.show_hide_dropdown.menu = self.make_show_hide_menu()
        self.show_hide_dropdown.on_click(event)
        return self.show_hide_dropdown

    def config_show_hide(self, settings):
        for key in self.show_hide.keys():
            self.show_hide[key] = settings[key]
        self.show_hide_dropdown.menu = self.make_show_hide_menu()
        self.update_visibility()


    def reshow_settings(self):
        self.unhide_button = Button(label="<", width=40, height=40, css_classes=["other_button"])
        self.unhide_button.sizing_mode = "fixed"
        self.unhide_button.visible = False

        def event(e):
            if self.session is not None:
                self.session.set_value(["settings", "interface", "show_hide", "tools"], True)
            self.toggle_hide("tools")
        self.unhide_button.on_click(event)
        return self.unhide_button

    def make_color_figure(self, palette, ticks):
        color_mapper = LinearColorMapper(palette=palette, low=0, high=1)
        color_figure = figure(tools='', height=0, width=SETTINGS_WIDTH)
        color_figure.x(0, 0)
        color_info = ColorBar(color_mapper=color_mapper, orientation="horizontal", 
                                   ticker=FixedTicker(ticks=ticks), width=SETTINGS_WIDTH)
        color_info.formatter = FuncTickFormatter(
                        args={"ticksx": [ticks[2], ticks[0], ticks[1], ticks[3]], "labelsx": ["[s", "[d", "d]", "s]"]},
                        code="""
                            var ret = "";
                            for (let i = 0; i < ticksx.length; i++)
                                if(tick == ticksx[i])
                                    ret += labelsx[i] + " ";
                            return ret;
                        """)
        color_info.major_label_policy = AllLabels()
        color_figure.add_layout(color_info, "below")

        # make plot invisible
        color_figure.axis.visible = False
        color_figure.toolbar_location = None
        color_figure.border_fill_alpha = 0
        color_figure.outline_line_alpha = 0

        return color_figure


    def to_readable_pos(self, x, genome_end, contig_names, contig_starts, lcs=0):
        x = int(x)
        oob = x > genome_end * self.session.get_value(["dividend"]) or x < 0
        if x < 0: 
            idx = 0
        elif x >= genome_end * self.session.get_value(["dividend"]): 
            idx = len(contig_names) - 1
            x -= contig_starts[-1]
        else:
            idx = 0
            for idx, (start, end) in enumerate(zip(contig_starts, contig_starts[1:] + \
                                                                  [genome_end * self.session.get_value(["dividend"])])):
                if x >= start and x < end:
                    x -= start
                    break

        if x == 0:
            label = "0 bp"
        elif x % 1000000 == 0:
            label = "{:,}".format(x / 1000000) + " mbp"
        elif x % 1000 == 0:
            label = "{:,}".format(x / 1000) + " kbp"
        else:
            label = "{:,}".format(x) + " bp"

        if idx >= len(contig_names):
            return "n/a"

        if lcs != 0:
            n = contig_names[idx][:-lcs]
        else:
            n = contig_names[idx]
        return n + ": " + label

    def set_area_range(self):
        contig_names_x = self.session.get_annotation_list(True)
        contig_names_y = self.session.get_annotation_list(False)
        contig_starts_x = self.session.get_tick_list(True)
        contig_starts_y = self.session.get_tick_list(False)
        lcs = self.session.get_longest_common_suffix()
        if len(contig_starts_x) > 0 and len(contig_starts_y) > 0:
            self.area_range_expected = "X: " + \
                self.to_readable_pos(math.floor(self.heatmap.x_range.start * self.session.get_value(["dividend"])), \
                                    contig_starts_x[-1], contig_names_x, \
                                    contig_starts_x[:-1], lcs) + " - " + \
                self.to_readable_pos(math.ceil(self.heatmap.x_range.end * self.session.get_value(["dividend"])), \
                                    contig_starts_x[-1], contig_names_x, \
                                    contig_starts_x[:-1], lcs) + " Y: " +\
                self.to_readable_pos(math.floor(self.heatmap.y_range.start * self.session.get_value(["dividend"])), \
                                    contig_starts_y[-1], contig_names_y, \
                                    contig_starts_y[:-1], lcs) + " - " + \
                self.to_readable_pos(math.ceil(self.heatmap.y_range.end * self.session.get_value(["dividend"])), \
                                    contig_starts_y[-1], contig_names_y, \
                                    contig_starts_y[:-1], lcs)
        else:
            self.area_range_expected = "n/a"
        self.area_range.value = self.area_range_expected

    def isfloat(self, num):
        try:
            float(num)
            return True
        except ValueError:
            return False

    def interpret_number(self, s):
        if s[-2:].lower() == "bp":
            s = s[:-2]
        fac = 1
        if len(s) > 0 and s[-1].lower() == "m":
            fac = 1000000
            s = s[:-1].strip()
        if len(s) > 0 and s[-1].lower() == "k":
            fac = 1000
            s = s[:-1].strip()
        s = s.replace(",", "")
        if self.isfloat(s):
            return float(s) * fac / self.session.get_value(["dividend"])
        return None

    def interpret_position(self, s, x_y, bot=True):
        if s.count(":") == 1:
            x, y = [i.strip() for i in s.split(":")]
            if "+-" in y:
                y1, y2 = [i.strip() for i in y.split("+-")]
                if len(y1) == 0:
                    b = 0
                else:
                    b = self.interpret_number(y1)
                c = self.interpret_number(y2)
                if not c is None and bot:
                    c = -c
                a = self.session.interpret_name(x, x_y, bot if len(y1) == 0 else True)
                if not a is None and not b is None and not c is None:
                    return [a + b + c]
            b = self.interpret_number(y)
            a = self.session.interpret_name(x, x_y, True)
            if not a is None and not b is None:
                return [a + b]

        a = self.interpret_number(s)
        if not a is None:
            return [a]

        if not s is None:
            a = self.session.interpret_name(s, x_y, bot)
            if not a is None:
                return [a]

        return [None]

    def interpret_range(self, s, x_y):
        if s.count(" - ") == 1 and s.count("[") <= 1 and s.count("]") <= 1:
            x, y = [i.strip() for i in s.split(" - ")]
            if x[:1] == "[":
                x = x[1:].strip()
            if y[-1:] == "]":
                y = y[:-1].strip()
            
            return self.interpret_position(x, x_y, True) + self.interpret_position(y, x_y, False)
        if s[:1] == "[":
            s = s[1:].strip()
        if s[-1:] == "]":
            s = s[:-1].strip()
        return self.interpret_position(s, x_y, True) + self.interpret_position(s, x_y, False)

    def interpret_area(self, s):
        s = s.lower()
        # @todo search does not work in other coordinate systems than genomic
        if s.count(";") == 1 and s.count("x:") == 0 and s.count("y:") == 0:
            x, y = [i.strip() for i in s.split(";")]
            if x[:2] == "x:":
                x = x[2:].strip()
            if y[:2] == "y:":
                y = y[2:].strip()
            return self.interpret_range(x, [True]) + self.interpret_range(y, [False])

        if s.count("x:") == 1 and s.count("y:") == 0:
            if s[:2] == "x:":
                s = s[2:].strip()
            return self.interpret_range(s, [True]) + [self.heatmap.y_range.start, self.heatmap.y_range.end]

        if s.count("x:") == 0 and s.count("y:") == 1:
            if s[:2] == "y:":
                s = s[2:].strip()
            return [self.heatmap.x_range.start, self.heatmap.x_range.end] + self.interpret_range(s, [True])

        if s.count("x:") == 1 and s.count("y:") == 1:
            x_pos = s.find("x:")
            y_pos = s.find("y:")
            x = (s[x_pos+2:y_pos] if x_pos < y_pos else s[x_pos+2:]).strip()
            y = (s[y_pos+2:x_pos] if y_pos < x_pos else s[y_pos+2:]).strip()
            print(x, y)
            return self.interpret_range(x, [True]) + self.interpret_range(y, [False])

        return self.interpret_range(s, [True, False]) + self.interpret_range(s, [False, True])


    def parse_area_range(self):
        if self.area_range_expected != self.area_range.value:
            # get minimal string
            s = self.area_range.value
            s = s.replace("\n", " ")
            s = s.replace("\t", " ")
            while "  " in s:
                s = s.replace("  ", " ")
            s = s.strip()

            i = self.interpret_area(s)
            if not i[0] is None and not i[1] is None:
                self.heatmap.x_range.start = min(i[0], i[1])
                self.heatmap.x_range.end = max(i[0], i[1], self.heatmap.x_range.start+1)
            elif not i[0] is None:
                self.heatmap.x_range.start = i[0]
            elif not i[1] is None:
                self.heatmap.x_range.end = max(i[1], self.heatmap.x_range.start+1)
            if not i[2] is None and not i[3] is None:
                self.heatmap.y_range.start = min(i[2], i[3])
                self.heatmap.y_range.end = max(i[2], i[3], self.heatmap.y_range.start+1)
            elif not i[2] is None:
                self.heatmap.y_range.start = i[2]
            elif not i[3] is None:
                self.heatmap.y_range.end = max(i[3], self.heatmap.y_range.start+1)

    def save_tools(self, tools):
        if not self.session is None:
            self.session.set_value(["settings", "active_tools"], tools.split(";"))

    def make_tabs(self, tabs, sizing_mode="stretch_both"):
        t = Tabs(tabs=tabs, sizing_mode=sizing_mode)
        def tab_active_change():
            # super convoluted and unnecessary code...
            # bokeh's UI becomes slow with too many buttons on one screen
            # therefore we hide tabs that are not active
            # however this unhiding the tabs triggers a layout problem
            # therefore instead of unhiding a tab, we create a new tab (that is visible by default) and set its
            # title and children to the hidden tabs title and children.
            # @note once bokeh fixes the layout/performance problem this code should just be removed
            self.curdoc.hold()
            for tab in t.tabs:
                tab.child.visible = False
            title = t.tabs[t.active].title
            children = t.tabs[t.active].child.children
            t.tabs[t.active] = Panel(title=title, child=column(children, visible=True))
            self.curdoc.unhold()

        t.on_change("active", lambda x, y, z: tab_active_change())
        t.tabs[t.active].child.visible = True
        return t

    def make_panel(self, title, tooltip="", children=[]):
        return Panel(title=title, child=column(children, visible=False))

    @gen.coroutine
    @without_document_lock
    def do_export(self):
        def unlocked_task():
            def callback():
                self.spinner.css_classes = ["fade-in"]
            self.curdoc.add_next_tick_callback(callback)

            if self.session.get_value(["settings", "export", "export_format"]) == "tsv":
                export_tsv(self.session, self.smoother_version)
            elif self.session.get_value(["settings", "export", "export_format"]) == "svg":
                print("unimplemented for now")
            else:
                print("invalid value for export_format")

            def callback():
                self.spinner.css_classes = ["fade-out"]
                self.print_status("done exporting.")
            self.curdoc.add_next_tick_callback(callback)
        yield executor.submit(unlocked_task)

    def __init__(self):
        self.show_hide = {"grid_lines": False, "contig_borders": True, "indent_line": False}
        self.hidable_plots = []
        self.grid_line_plots = []
        self.unhide_button = None
        self.render_areas = {}
        self.slope = None
        self.show_hide_dropdown = None
        self.names = None

        self.x_coords_d = "full_genome"
        self.y_coords_d = "full_genome"

        self.do_render = False
        self.force_render = True
        self.curdoc = curdoc()
        self.last_drawing_area = (0, 0, 0, 0)
        self.curr_area_size = 1
        self.smoother_version = "?"
        self.reset_options = {}
        self.session = bin.global_variables.quarry_session
        with open(SMOOTHER_PATH + '/static/conf/default.json', 'r') as f:
            self.settings_default = json.load(f)

        self.heatmap = None
        d = {"screen_bottom": [], "screen_left": [], "screen_top": [], "screen_right": [], "color": [], 
             "chr_x": [], "chr_y": [], "index_left": [], "index_right": [],
             "index_bottom": [], "index_top": [], "score_total": [], "score_a": [], "score_b": [],
             "chr_x_symmetry" : [], "chr_y_symmetry" : [], "index_symmetry_left" : [], 
             "index_symmetry_right" : [], "index_symmetry_bottom" : [], "index_symmetry_top" : []}
        self.heatmap_data = ColumnDataSource(data=d)
        d = {"b": [], "l": [], "t": [], "r": []}
        self.overlay_data = ColumnDataSource(data=d)
        self.overlay_dataset_id = None
        self.heatmap_x_axis = None
        self.heatmap_x_axis_2 = None
        self.heatmap_y_axis = None
        self.heatmap_y_axis_2 = None
        self.raw_x = None
        self.raw_x_axis = None
        self.raw_y = None
        self.raw_y_axis = None
        d_x = {
            "chrs": [],
            "index_start": [],
            "index_end": [],
            "screen_pos": [],
            "values": [],
            "colors": [],
            "names": [],
        }
        d_y = {
            "chrs": [],
            "index_start": [],
            "index_end": [],
            "screen_pos": [],
            "values": [],
            "colors": [],
            "names": [],
        }
        self.raw_data_x = ColumnDataSource(data=d_x)
        self.raw_data_y = ColumnDataSource(data=d_y)
        self.anno_x = None
        self.anno_x_axis = None
        self.anno_y = None
        self.anno_y_axis = None
        d = {"anno_name": [], "screen_start": [], "screen_end": [], "color": [], "chr": [],
             "index_start": [], "index_end": [], "info": [], "num_anno": [], "size": [], "strand": [], "id": [], "desc": []}
        self.anno_x_data = ColumnDataSource(data=d)
        self.anno_y_data = ColumnDataSource(data=d)
        self.meta_file = None
        self.min_max_bin_size = None
        self.info_status_bar = None
        self.spinner = None
        self.info_field = None
        self.settings_row = None
        self.slider_spinner_config = []
        self.range_slider_spinner_config = []
        self.dropdown_select_config = []
        self.checkbox_config = []
        self.multi_choice_config = []
        self.export_file = None
        self.ticker_x = None
        self.ticker_x_2 = None
        self.ticker_y = None
        self.ticker_y_2 = None
        self.tick_formatter_x = None
        self.tick_formatter_x_2 = None
        self.tick_formatter_y = None
        self.tick_formatter_y_2 = None
        self.undo_button = None
        self.redo_button = None
        self.color_layout = None
        self.area_range = None
        self.area_range_expected = "n/a"
        self.set_active_tools_ti = None
        d = {
            "chrs": [],
            "index_start": [],
            "index_end": [],
            "xs": [],
            "ys": [],
            "colors": [],
            "anno_desc": [],
            "sample_id": [],
            "anno_idx": [],
        }
        self.ranked_columns_data = ColumnDataSource(data=d)
        self.ranked_columns = None
        self.ranked_rows_data = ColumnDataSource(data=d)
        self.ranked_rows = None
        d = {
            "chr": [],
            "color": [],
            "xs": [],
            "ys": []
        }
        self.dist_dep_dec_plot_data = ColumnDataSource(data=d)
        self.dist_dep_dec_plot = None
        self.log_div = None
        self.log_div_text = ""

        self.do_layout()

    def do_layout(self):
        global SETTINGS_WIDTH
        tollbars = []
        self.heatmap = FigureMaker().range1d().scale().combine_tools(tollbars).get(self)
        self.heatmap.min_border_left = 3
        self.heatmap.min_border_right = 3
        self.heatmap.min_border_bottom = 3
        self.heatmap.min_border_top = 3
        self.heatmap.border_fill_color = None

        self.heatmap.quad(left="screen_left", bottom="screen_bottom", right="screen_right", top="screen_top", 
                          fill_color="color", line_color=None, source=self.heatmap_data, level="underlay")
        self.heatmap.xgrid.minor_grid_line_alpha = 0.5
        self.heatmap.ygrid.minor_grid_line_alpha = 0.5

        self.heatmap.quad(left="l", bottom="b", right="r", top="t", fill_color=None, line_color="red", 
                            source=self.overlay_data, level="underlay")

        self.overlay_dataset_id = Spinner(title="Overlay Lines Dataset Id", low=-1, step=1, value=-1, 
                                          width=DEFAULT_SIZE, mode="int")
        self.overlay_dataset_id.on_change("value_throttled", lambda x, y, z: self.trigger_render())


        self.heatmap.add_tools(HoverTool(
            tooltips=[
                ('(x, y)', "(@chr_x @index_left - @index_right, @chr_y @index_bottom - @index_top)"),
                ('sym(x, y)', "(@chr_x_symmetry @index_symmetry_left - @index_symmetry_right, @chr_y_symmetry @index_symmetry_bottom - @index_symmetry_top)"),
                ('score', "@score_total"),
                ('reads by group', "A: @score_a, B: @score_b")
            ]
        ))

        self.heatmap_x_axis = FigureMaker().x_axis_of(
            self.heatmap, self, "", True, hide_keyword="coords").combine_tools(tollbars).get(self)
        self.heatmap_x_axis_2 = FigureMaker().x_axis_of(
            self.heatmap, self, "", True, hide_keyword="regs").combine_tools(tollbars).get(self)
    
        #self.heatmap_x_axis.xaxis.minor_tick_line_color = None
        self.heatmap_y_axis = FigureMaker().y_axis_of(
            self.heatmap, self, "", True, hide_keyword="coords").combine_tools(tollbars).get(self)
        self.heatmap_y_axis_2 = FigureMaker().y_axis_of(
            self.heatmap, self, "", True, hide_keyword="regs").combine_tools(tollbars).get(self)
        #self.heatmap_y_axis.yaxis.minor_tick_line_color = None

        self.slope = Slope(gradient=1, y_intercept=0, line_color=None)
        self.heatmap.add_layout(self.slope)


        raw_hover_x = HoverTool(
            tooltips="""
                <div>
                    <span style="color: @colors">@names: $data_x</span>
                </div>
            """,
            mode='hline'
        )
        raw_hover_y = HoverTool(
            tooltips="""
                <div>
                    <span style="color: @colors">@names: $data_y</span>
                </div>
            """,
            mode='vline'
        )

        self.raw_x = FigureMaker().w(DEFAULT_SIZE).link_y(
            self.heatmap).hidden().hide_on("raw", self).combine_tools(tollbars).get(self)
        self.raw_x.add_tools(raw_hover_x)
        self.raw_x_axis = FigureMaker().x_axis_of(
            self.raw_x, self).combine_tools(tollbars).get(self)
        self.raw_x_axis.xaxis.axis_label = "Cov."
        self.raw_x_axis.xaxis.ticker = AdaptiveTicker(desired_num_ticks=3, num_minor_ticks=0)
        self.raw_x.xgrid.ticker = AdaptiveTicker(desired_num_ticks=3, num_minor_ticks=1)
        self.raw_x.xgrid.grid_line_alpha = 0
        self.raw_x.xgrid.minor_grid_line_alpha = 0.5
        self.raw_x.ygrid.minor_grid_line_alpha = 0.5

        self.raw_y = FigureMaker().h(DEFAULT_SIZE).link_x(
            self.heatmap).hidden().hide_on("raw", self).combine_tools(tollbars).get(self)
        self.raw_y.add_tools(raw_hover_y)
        self.raw_y_axis = FigureMaker().y_axis_of(
            self.raw_y, self).combine_tools(tollbars).get(self)
        self.raw_y_axis.yaxis.axis_label = "Cov."
        self.raw_y_axis.yaxis.ticker = AdaptiveTicker(desired_num_ticks=3, num_minor_ticks=0)
        self.raw_y.ygrid.ticker = AdaptiveTicker(desired_num_ticks=3, num_minor_ticks=1)
        self.raw_y.ygrid.grid_line_alpha = 0
        self.raw_y.ygrid.minor_grid_line_alpha = 0.5
        self.raw_y.xgrid.minor_grid_line_alpha = 0.5

        self.raw_x.multi_line(xs="values", ys="screen_pos", source=self.raw_data_x,
                        line_color="colors")  # , level="image"
        self.raw_y.multi_line(xs="screen_pos", ys="values", source=self.raw_data_y,
                        line_color="colors")  # , level="image"

        self.anno_x = FigureMaker().w(DEFAULT_SIZE).link_y(self.heatmap).hidden().hide_on(
            "annotation", self).combine_tools(tollbars).categorical_x().get(self)
        self.anno_x_axis = FigureMaker().x_axis_of(
            self.anno_x, self).combine_tools(tollbars).get(self)
        self.anno_x_axis.xaxis.axis_label = "Anno."
        self.anno_x.xgrid.minor_grid_line_alpha = 0
        self.anno_x.xgrid.grid_line_alpha = 0
        self.anno_x.ygrid.minor_grid_line_alpha = 0.5

        self.anno_y = FigureMaker().h(DEFAULT_SIZE).link_x(self.heatmap).hidden().hide_on(
            "annotation", self).combine_tools(tollbars).categorical_y().get(self)
        self.anno_y_axis = FigureMaker().y_axis_of(
            self.anno_y, self).combine_tools(tollbars).get(self)
        self.anno_y_axis.yaxis.axis_label = "Anno."
        self.anno_y.ygrid.minor_grid_line_alpha = 0
        self.anno_y.ygrid.grid_line_alpha = 0
        self.anno_y.xgrid.minor_grid_line_alpha = 0.5

        self.anno_x.vbar(x="anno_name", top="screen_end", bottom="screen_start", width="size", fill_color="color", 
                         line_color=None,
                         source=self.anno_x_data)
        self.anno_y.hbar(y="anno_name", right="screen_end", left="screen_start", height="size", fill_color="color",
                         line_color=None,
                         source=self.anno_y_data)

        anno_hover = HoverTool(
            tooltips=[
                ('bin pos', "@chr @index_start - @index_end"),
                ('num_annotations', "@num_anno"),
                ('ID', "@id"),
                ('strand', "@strand"),
                ('description', "@desc"),
                ('add. info', "@info"),
            ]
        )
        self.anno_x.add_tools(anno_hover)
        self.anno_y.add_tools(anno_hover)
        
        ranked_hover = HoverTool(
            tooltips=[
                ('pos', "@chrs @index_start - @index_end"),
                ('ranking', "@xs"),
                ('coverage', "@ys"),
                ('desc', "@anno_desc"),
                ('anno. index', "@anno_idx"),
                ('sample index', "@sample_id")
            ]
        )
        self.ranked_columns = figure(tools="pan,wheel_zoom,box_zoom,crosshair",
                                     y_axis_type="log", height=200, width=SETTINGS_WIDTH)
        tollbars.append(self.ranked_columns.toolbar)
        self.ranked_columns.dot(x="xs", y="ys", color="colors", size=12, source=self.ranked_columns_data)
        self.ranked_columns.xaxis.axis_label = "Samples ranked by RNA reads per kbp"
        self.ranked_columns.yaxis.axis_label = "RNA reads per kbp"
        self.ranked_columns.add_tools(ranked_hover)

        self.ranked_rows = figure(tools="pan,wheel_zoom,box_zoom,crosshair", 
                                  y_axis_type="log", height=200, width=SETTINGS_WIDTH)
        self.ranked_rows.toolbar_location = None
        self.ranked_rows.dot(x="xs", y="ys", color="colors", size=12, source=self.ranked_rows_data)
        self.ranked_rows.xaxis.axis_label = "Samples ranked by max. DNA reads in bin"
        self.ranked_rows.yaxis.axis_label = "Maximal DNA reads in bin"
        self.ranked_rows.add_tools(ranked_hover)
        
        self.dist_dep_dec_plot = figure(title="Distance Dependant Decay", tools="pan,wheel_zoom,box_zoom,crosshair",
                                        y_axis_type="log", height=200, width=SETTINGS_WIDTH)
        self.dist_dep_dec_plot.xaxis.axis_label = "manhatten distance from diagonal"
        self.dist_dep_dec_plot.yaxis.axis_label = "reads per kbp^2"
        self.dist_dep_dec_plot.multi_line(xs="xs", ys="ys", color="color",
                                          source=self.dist_dep_dec_plot_data)

        for p in [self.ranked_columns, self.ranked_rows, self.dist_dep_dec_plot]:
            p.sizing_mode = "stretch_width"
            p.toolbar_location = None
            tollbars.append(p.toolbar)
            p.xaxis.axis_label_text_font_size = "11px"
            p.yaxis.axis_label_text_font_size = "11px"
            p.xaxis.axis_label_standoff = 0
            p.yaxis.axis_label_standoff = 0
            p.xaxis.major_label_text_font = FONT
            p.yaxis.major_label_text_font = FONT
            p.xaxis.axis_label_text_font = FONT
            p.yaxis.axis_label_text_font = FONT
            p.dot(x=[1],y=[1],fill_alpha=0,line_alpha=0)

        self.dist_dep_dec_plot.xaxis[0].formatter = FuncTickFormatter(
            args={},
            code="""
                    function numberWithCommas(x) {
                        return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
                    }
                    var tick_label = "";
                    if(tick == 0)
                        tick_label = "0 bp"
                    else if(tick % 1000000 == 0)
                        tick_label = numberWithCommas(tick / 1000000) + " mbp";
                    else if (tick % 1000 == 0)
                        tick_label = numberWithCommas(tick / 1000) + " kbp";
                    else
                        tick_label = numberWithCommas(tick) + " bp";
                    return tick_label;
                """)
        self.dist_dep_dec_plot.add_tools(HoverTool(
            tooltips="""
                <div>
                    <span style="color: @color">@chr: ($data_x, $data_y)</span>
                </div>
            """
        ))

        crosshair = CrosshairTool(dimensions="width", line_color="lightgrey")
        for fig in [self.anno_x, self.raw_x, self.heatmap]:
            fig.add_tools(crosshair)
        crosshair = CrosshairTool(dimensions="height", line_color="lightgrey")
        for fig in [self.anno_y, self.raw_y, self.heatmap]:
            fig.add_tools(crosshair)

        tool_bar = FigureMaker.get_tools(tollbars)
        show_hide = self.make_show_hide_dropdown(
            ["settings", "interface", "show_hide"],
                ("Secondary Axes", "axis"),("Coordinates", "coords"),("Regions", "regs"), (RAW_PLOT_NAME, "raw"),
                                                   (ANNOTATION_PLOT_NAME, "annotation"), ("Options Panel", "tools"))

        in_group = self.dropdown_select("Merge datasets by", "tooltip_in_group",
                                             ("Sum [a+b+c+...]", "sum"), 
                                             ("Minimium [min(a,b,c,...)]", "min"),
                                             ("Maximum [max(a,b,c,...)]", "max"),
                                             ("Difference [|a-b|+|a-c|+|b-c|+...]", "dif"),
                                             ("Mean [mean(a,b,c,...)]", "mean"),
                                             active_item=['settings', 'replicates', 'in_group'])

        betw_group = self.dropdown_select("Compare datapools by", "tooltip_between_groups",
                                               ("Sum [a+b]", "sum"), ("Show First Group [a]", "1st"), 
                                               ("Show Second Group [b]", "2nd"), ("Substract [a-b]", "sub"),
                                               ("Difference [|a-b|]", "dif"), ("Divide [a/b]", "div"),
                                               ("Minimum [min(a,b)]", "min"),  ("Maximum [max(a,b)]", "max"),
                                                active_item=['settings', 'replicates', 'between_group'])

        symmetrie = self.dropdown_select("Symmetry", "tooltip_symmetry",
                                              ("Show All Interactions", "all"), 
                                              ("Only Show Symmetric Interactions", "sym"),
                                              ("Only Show Asymmetric Interactions", "asym"),
                                              ("Make Interactions Symmetric (Bottom to Top)", "topToBot"), 
                                              ("Make Interactions Symmetric (Top to Bottom)", "botToTop"),
                                              active_item=['settings', 'filters', 'symmetry'])

        if Quarry.has_cooler_icing():
            normalization = self.dropdown_select("Normalize heatmap by", "tooltip_normalize_by",
                                                    ("Reads per million",
                                                    "rpm"), 
                                                    ("Reads per thousand",
                                                    "rpk"), 
                                                    ("Binominal test", "radicl-seq"),
                                                    ("Iterative Correction", "hi-c"),
                                                    ("Associated slices", "grid-seq"),
                                                    ("Cooler Iterative Correction", "cool-hi-c"),
                                                    ("No normalization", "dont"),
                                                    active_item=['settings', 'normalization', 'normalize_by']
                                                    )
        else:
            normalization = self.dropdown_select("Normalize heatmap by", "tooltip_normalize_by",
                                                    ("Reads per million",
                                                    "rpm"), 
                                                    ("Reads per thousand",
                                                    "rpk"), 
                                                    ("Binominal test", "radicl-seq"),
                                                    ("Iterative Correction", "hi-c"),
                                                    ("Associated slices", "grid-seq"),
                                                    ("No normalization", "dont"),
                                                    active_item=['settings', 'normalization', 'normalize_by']
                                                    )
        normalization_cov = self.dropdown_select("Normalize coverage by", "tooltip_normalize_by_coverage",
                                                  ("Reads per million",
                                                   "rpm"), 
                                                  ("Reads per thousand",
                                                   "rpk"), 
                                                  ("Reads per million base pairs", "rpmb"),
                                                  ("Reads per thousand base pairs", "rpkb"),
                                                  ("No normalization", "dont"),
                                                  active_item=['settings', 'normalization', 'normalize_by_coverage']
                                                  )

        color_scale = self.dropdown_select("Scale Color Range", "tooltip_scale_color_range",
                                                  ("absolute max [x' = x / max(|v| in V)]", "abs"), 
                                                  ("max [x' = x / max(v in V)]", "max"), 
                                    ("min-max [x' = (x + min(v in V)) / (max(v in V) - min(v in V))]", "minmax"), 
                                                  ("do not scale [x' = x]", "dont"),
                                                  active_item=['settings', 'normalization', 'scale']
                                                  )

        incomp_align_layout = self.make_checkbox("Show multi-mapping reads with incomplete mapping loci lists", 
                                                    "tooltip_incomplete_alignments",
                                                    settings=['settings', 'filters', 'incomplete_alignments'])

        #divide_column = self.make_checkbox("Divide heatmap columns by track", "tooltip_divide_column",
        #                                            settings=['settings', 'normalization', 'divide_by_column_coverage'])
        #divide_row = self.make_checkbox("Divide heatmap rows by track", "tooltip_divide_row",
        #                                            settings=['settings', 'normalization', 'divide_by_row_coverage'])


        ddd = self.make_checkbox("Normalize Primary data", "tooltip_ddd",
                                        settings=['settings', 'normalization', 'ddd'])
        ddd_show = self.make_checkbox("Display", "tooltip_ddd_show",
                                        settings=['settings', 'normalization', 'ddd_show'])
        ddd_ex_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_ddd_quantiles",
                                                title="Percentile of samples to keep [%]",
                                                settings=["settings", "normalization", "ddd_quantile"], 
                                                sizing_mode="stretch_width")
        ice_sparse_filter = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_ice_sparse_filter",
                                                title="filter out slices with too many empty bins [%]", 
                                                settings=["settings", "normalization", "ice_sparse_slice_filter"], 
                                                sizing_mode="stretch_width")
        ddd_sam_l = self.make_range_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_ddd_samples",
                                                title="Number of samples", 
                                                settings=["settings", "normalization", "ddd_samples"], 
                                                sizing_mode="stretch_width")

        square_bins = self.make_checkbox("Make Bins Squares", "tooltip_bin_aspect_ratio",
                                                   settings=['settings', "interface", "squared_bins"]
                                                   )

        power_ten_bin = self.make_checkbox("Snap Bin Size", "tooltip_snap_bin_size",
                                                settings=['settings', "interface", "snap_bin_size"]
                                            )

        color_picker = self.dropdown_select("Color Palette", "tooltip_color",
                                                ("Viridis", "Viridis256"),
                                                ("Plasma", "Plasma256"),
                                                ("Turbo", "Turbo256"),
                                                ("Low to High", "LowToHigh"),
                                                active_item=['settings', "interface", "color_palette"]
                                                  )

        multi_mapping = self.dropdown_select("Multi-Mapping reads (MMR)", "tooltip_multi_mapping",
                                                ("Count MMR if all mapping loci are within the same bin", "enclosed"),
                                                ("Count MMR if mapping loci minimum bounding-box overlaps bin", "overlaps"),
                                                ("Count MMR if bottom left mapping loci is within a bin", "first"),
                                                ("Count MMR if top right mapping loci is within a bin", "last"),
                                                ("Ignore MMRs", "points_only"),
                                                active_item=['settings', "filters", "ambiguous_mapping"]
                                                  )

        def axis_labels_event(e):
            self.session.set_value(["seetings", "interface", "axis_lables"], e)
            self.heatmap_y_axis_2.yaxis.axis_label = e.split("_")[0]
            self.heatmap_x_axis_2.xaxis.axis_label = e.split("_")[1]
        axis_lables = self.dropdown_select("Axis Labels", "tooltip_y_axis_label",
                                                  ("RNA / DNA", "RNA_DNA"),
                                                  ("DNA / RNA", "DNA_RNA"),
                                                  ("DNA / DNA", "DNA_DNA"), 
                                                  active_item=['settings', "interface", "axis_lables"],
                                                  event=axis_labels_event
                                                  )

        def stretch_event(val):
            self.session.set_value(["settings", "interface", "stretch"], val)
            if val:
                self.heatmap.sizing_mode = "stretch_both"
            else:
                self.heatmap.sizing_mode = "scale_height"
        stretch = self.make_checkbox("Stretch heatmap", "tooltip_stretch_scale",
                                            settings=["settings", "interface", "stretch"],
                                            on_change=stretch_event)

        ms_l = self.make_range_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_map_q_bounds",
                                                settings=["settings", "filters", "mapping_q"], 
                                                title="Mapping Quality Bounds", sizing_mode="stretch_width")

        ibs_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_minimum_interactions",
                                                title="read-count adjustment", 
                                                settings=["settings", "normalization", "min_interactions"], 
                                                sizing_mode="stretch_width")

        crs_l = self.make_range_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_color_scale_range",
                                                title="Color Scale Range", 
                                                settings=["settings", "normalization", "color_range"],
                                                sizing_mode="stretch_width")

        is_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_color_scale_log_base",
                                          title="Color Scale Log Base", 
                                          settings=["settings", "normalization", "log_base"],
                                          sizing_mode="stretch_width")

        def update_freq_event(val):
            self.session.set_value(["settings", "interface", "update_freq", "val"], val)
        ufs_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_update_frequency",
                                            settings=["settings", "interface", "update_freq"],
                                            title="Update Frequency [seconds]", #, format="0[.]000"
                                            on_change=update_freq_event, sizing_mode="stretch_width")

        rs_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_redraw_zoom",
                                    settings=["settings", "interface", "zoom_redraw"],
                                    title="Redraw if zoomed in by [%]", sizing_mode="stretch_width")

        aas_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_add_draw_area",
                                        settings=["settings", "interface", "add_draw_area"],
                                         title="Additional Draw Area [%]", sizing_mode="stretch_width")

        dds_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_min_diag_dist",
                                    settings=["settings", "filters", "min_diag_dist"],
                                       title="Minimum Distance from Diagonal [kbp]", sizing_mode="stretch_width")

        def anno_size_slider_event(val):
            self.session.set_value(["settings", "interface", "anno_size", "val"], val)
            self.anno_x.width = val
            self.anno_x_axis.width = val
            self.anno_y.height = val
            self.anno_y_axis.height = val
        ass_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_anno_size",
                                      settings=["settings", "interface", "anno_size"],
                                       title=ANNOTATION_PLOT_NAME + " Size [pixel]", sizing_mode="stretch_width",
                                       on_change=anno_size_slider_event)

        def raw_size_slider_event(val):
            self.session.set_value(["settings", "interface", "raw_size", "val"], val)
            self.raw_x.width = val
            self.raw_x_axis.width = val
            self.raw_y.height = val
            self.raw_y_axis.height = val
        rss2_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_raw_size",
                                      settings=["settings", "interface", "raw_size"],
                                      title=RAW_PLOT_NAME + " Size [pixel]", sizing_mode="stretch_width",
                                      on_change=raw_size_slider_event)

        nb_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_max_number_of_bins",
                               settings=["settings", "interface", "max_num_bins"],
                               title="Max number of Bins [in thousands]", sizing_mode="stretch_width")

        rsa_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_p_accept",
                               settings=["settings", "normalization", "p_accept"],
                               title="pAccept for binominal test", sizing_mode="stretch_width")
        bsmcq_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="@todo",
                               settings=["settings", "normalization", "grid_seq_max_bin_size"],
                               title="Section size max coverage [bp]", sizing_mode="stretch_width")
        grid_seq_samples_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="tooltip_section_size_max_coverage",
                               settings=["settings", "normalization", "grid_seq_samples"],
                               title="Number of samples", sizing_mode="stretch_width")
        radicl_seq_samples_l = self.make_slider_spinner(width=SETTINGS_WIDTH, tooltip="@todo",
                               settings=["settings", "normalization", "radicl_seq_samples"],
                               title="Number of samples", sizing_mode="stretch_width")
        grid_seq_display_background = self.make_checkbox("Display Background as Secondary Data", 
                                                "@todo",
                                                settings=['settings', "normalization", "grid_seq_display_background"]
                                            )
        radicl_seq_display_coverage = self.make_checkbox("Display Coverage as Secondary Data", 
                                                "@todo",
                                                settings=['settings', "normalization", "radicl_seq_display_coverage"]
                                            )
        grid_seq_column = self.make_checkbox("Compute Background for Columns", 
                                                "@todo",
                                                settings=['settings', "normalization", "grid_seq_axis_is_column"]
                                            )
        radicl_seq_column = self.make_checkbox("Apply binominal test on Columns", 
                                                "@todo",
                                                settings=['settings', "normalization", "radicl_seq_axis_is_column"]
                                            )
        grid_seq_intersection = self.make_checkbox(
                                                "Use intersection between replicates", 
                                                "@todo",
                                                settings=['settings', "normalization", "grid_seq_filter_intersection"]
                                            )
        grid_seq_anno = self.dropdown_select_session("Annotation type", "@todo",
                                                ["annotation", "list"], 
                                                ['settings', "normalization", "grid_seq_annotation"])
        grid_seq_rna_filter_l = self.make_range_slider_spinner(width=SETTINGS_WIDTH, 
                               tooltip="@todo",
                               settings=["settings", "normalization", "grid_seq_rna_filter"],
                               title="RNA reads per kbp bounds", sizing_mode="stretch_width")
        grid_seq_dna_filter_l = self.make_range_slider_spinner(width=SETTINGS_WIDTH, 
                               tooltip="@todo",
                               settings=["settings", "normalization", "grid_seq_dna_filter"],
                               title="Maximal DNA reads in bin bounds", sizing_mode="stretch_width")

        group_layout = self.multi_choice_auto("Active Primary Datasets", "tooltip_replicates", 
                                                [[["replicates", "in_group_a"], "Datapool A"], 
                                                [["replicates", "in_group_b"], "Datapool B"]],
                                                ["replicates", "list"])

        annos_layout = self.multi_choice_auto("Visible Annotations", "tooltip_annotations",
                                                         [[["annotation", "visible_y"], "Row"],
                                                          [["annotation", "visible_x"], "Column"]],
                                                        ["annotation", "list"])

        power_tick = FuncTickFormatter(
            code="""
            if (tick / 9 >= 7)
                return Math.ceil((1 + tick % 9)) + "*10^" + Math.floor(tick / 9) + "bp";
            else if (tick / 9 >= 3)
                return Math.ceil((1 + tick % 9) * Math.pow(10, Math.floor(tick / 9)-3)) + "kbp";
            else
                return Math.ceil((1 + tick % 9) * Math.pow(10, Math.floor(tick / 9))) + "bp"; """)
        self.min_max_bin_size = Slider( 
                start = 0,
                end = 1,
                value=0,
                title="Minimum Bin Size",
                format=power_tick, 
                sizing_mode="stretch_width",
                css_classes=["tooltip", "tooltip_min_bin_size"],
                height=40)
        def min_bin_size_event():
            self.session.set_value(["settings", "interface", "min_bin_size", "val"], self.min_max_bin_size.value)
            self.trigger_render()
        self.min_max_bin_size.on_change("value_throttled", lambda x, y, z: min_bin_size_event())

        def callback(a):
            self.min_max_bin_size.value = \
                min(max(self.min_max_bin_size.value + a, self.min_max_bin_size.start), self.min_max_bin_size.end)
            min_bin_size_event()
        button_s_up = Button(label="", css_classes=["other_button", "fa_sort_up_solid"], 
                                button_type="light", width=10, height=10)
        button_s_up.on_click(lambda _: callback(1))
        button_s_down = Button(label="", css_classes=["other_button", "fa_sort_down_solid"],
                                button_type="light", width=10, height=10)
        button_s_down.on_click(lambda _: callback(-1))

        mmbs_l = row([self.min_max_bin_size, column([button_s_up, button_s_down])], margin=DIV_MARGIN)

        self.info_status_bar = Div(text="Waiting for Fileinput.", sizing_mode="stretch_width")
        self.info_status_bar.height = 26
        self.info_status_bar.min_height = 26
        self.info_status_bar.max_height = 26
        self.info_status_bar.height_policy = "fixed"

        status_bar_row = row([self.info_status_bar], sizing_mode="stretch_width", css_classes=["top_border"])
        
        self.spinner = Div(text="<div class=\"lds-spinner\"><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div><div></div></div>")
        self.spinner.css_classes = ["fade-out"]

        norm_layout = self.multi_choice_auto("Active Secondary Datasets", "tooltip_coverage_normalization",
                                                       [[["coverage", "cov_column_a"], "Column - Datapool A"], 
                                                        [["coverage", "cov_column_b"], "Column - Datapool B"], 
                                                        [["coverage", "cov_row_a"], "Row - Datapool A"], 
                                                        [["coverage", "cov_row_b"], "Row - Datapool B"]],
                                                        ["coverage", "list"])

        x_coords = self.dropdown_select_session("Column Coordinates", "tooltip_row_coordinates",
                                                ["annotation", "list"], 
                                                ["contigs", "column_coordinates"], 
                                                [("Genomic loci", "full_genome")])

        y_coords = self.dropdown_select_session("Row Coordinates", "tooltip_column_coordinates",
                                                ["annotation", "list"], 
                                                ["contigs", "row_coordinates"], 
                                                [("Genomic loci", "full_genome")])

        chrom_layout = self.multi_choice_auto("Active Contigs", "tooltip_chromosomes",
                                                        [[["contigs", "displayed_on_x"], "Row"], 
                                                         [["contigs", "displayed_on_y"], "Column"]],
                                                        ["contigs", "list"])

        multiple_anno_per_bin = self.dropdown_select("Multiple Annotations in Bin", 
                "tooltip_multiple_annotations_in_bin", 
                ("Combine region from first to last annotation", "combine"), 
                ("Use first annotation in Bin", "first"), 
                ("Use one prioritized annotation. (stable while zoom- and pan-ing)", "max_fac_pow_two"), 
                ("Increase number of bins to match number of annotations (might be slow)", "force_separate"),
                active_item=["settings", "filters", "multiple_annos_in_bin"])
        multiple_bin_per_anno = self.dropdown_select("Multiple Bins for Annotation", 
                "tooltip_multiple_bin_for_anno", 
                ("Show several bins for the annotation", "separate"), 
                ("Stretch one bin over entire annotation", "stretch"), 
                ("Make all annotations size 1", "squeeze"), 
                active_item=["settings", "filters", "anno_in_multiple_bins"])

        export_button = Button(label="Export", width=SETTINGS_WIDTH, sizing_mode="fixed", 
                                    css_classes=["other_button", "tooltip", "tooltip_export"], height=DROPDOWN_HEIGHT)
        def exp_event(x):
            self.do_export()
        export_button.on_click(exp_event)

        export_format = self.dropdown_select("Format", 
                "tooltip_export_format", 
                ("TSV-file", "tsv"), 
                ("SVG-file", "svg"), 
                active_item=["settings", "export", "export_format"])
        
        export_full = self.make_checkbox("Export full matrix instead", "tooltip_full_matrix",
                                            settings=["settings", "export", "do_export_full"])

        export_label = Div(text="Output Prefix:", css_classes=["tooltip", "tooltip_export_prefix"])
        export_label.margin = DIV_MARGIN
        self.export_file = TextInput(css_classes=["tooltip", "tooltip_export_prefix"], height=DEFAULT_TEXT_INPUT_HEIGHT,
                                     width=SETTINGS_WIDTH)
        def export_file_event(_1, _2, _3):
            self.session.set_value(["settings", "export", "prefix"], self.export_file.value)
        self.export_file.on_change("value", export_file_event)
        
        export_sele_layout = self.multi_choice_auto("Export Selection", "tooltip_export_selection", [[["settings", "export", "selection"], ""]],
                                                    ["settings", "export", "list"], orderable=False)
    
        self.low_color = ColorPicker(title="Color Low", css_classes=["tooltip", "tooltip_color_low"],
                                     height=DEFAULT_TEXT_INPUT_HEIGHT*2)
        self.high_color = ColorPicker(title="Color High", css_classes=["tooltip", "tooltip_color_high"],
                                     height=DEFAULT_TEXT_INPUT_HEIGHT*2)
        def color_event_low(_1, _2, _3):
            self.session.set_value(["settings", "interface", "color_low"], self.low_color.color)
            self.trigger_render()
        def color_event_high(_1, _2, _3):
            self.session.set_value(["settings", "interface", "color_high"], self.high_color.color)
            self.trigger_render()
        self.low_color.on_change("color", color_event_low)
        self.high_color.on_change("color", color_event_high)


        with open(SMOOTHER_PATH + "/VERSION", "r") as in_file:
            self.smoother_version = in_file.readlines()[0][:-1]

        version_info = Div(text="Smoother "+ self.smoother_version +"<br>LibSps Version: " + Quarry.get_libSps_version())

        self.color_layout = row([self.make_color_figure(["black"], [0,0,0,0])], 
                                css_classes=["tooltip", "tooltip_color_layout"])


        quick_configs = [self.config_row("default", lock_name=True)]
        for idx in range(1,7):
            quick_configs.append(self.config_row(idx))

        SYM_WIDTH = 10
        SYM_CSS = ["other_button"]
        reset_session = Button(label="", css_classes=SYM_CSS + ["fa_reset"], width=SYM_WIDTH, 
                                  height=SYM_WIDTH, sizing_mode="fixed", button_type="light", align="center")
        def reset_event():
            with open(self.meta_file.value + ".smoother_index/default_session.json", 'r') as f:
                default_session = json.load(f)
                default_session["settings"] = self.session.get_value(["settings"])
            self.session.set_session(default_session)
            self.do_config()
            self.trigger_render()

        reset_session.on_click(reset_event)

        self.ticker_x = ExtraTicksTicker(extra_ticks=[])
        self.ticker_x_2 = IntermediateTicksTicker(extra_ticks=[])
        self.ticker_y = ExtraTicksTicker(extra_ticks=[])
        self.ticker_y_2 = IntermediateTicksTicker(extra_ticks=[])

        def get_formatter_tick():
            return FuncTickFormatter(
                    args={"contig_starts": [], "genome_end": 0, "dividend": 1},
                    code="""
                            function numberWithCommas(x) {
                                return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
                            }
                            if(tick < 0 || tick >= genome_end)
                                return "n/a";
                            var idx = 0;
                            while(contig_starts[idx + 1] <= tick)
                                idx += 1;
                            var tick_pos = dividend * (tick - contig_starts[idx]);
                            var tick_label = "";
                            if(tick_pos == 0)
                                tick_label = "0 bp"
                            else if(tick_pos % 1000000 == 0)
                                tick_label = numberWithCommas(tick_pos / 1000000) + " mbp";
                            else if (tick_pos % 1000 == 0)
                                tick_label = numberWithCommas(tick_pos / 1000) + " kbp";
                            else
                                tick_label = numberWithCommas(tick_pos) + " bp";
                            return tick_label;
                        """)
        def get_formatter_chr(x):
            return FuncTickFormatter(
                    args={"contig_starts": [], "genome_end": 0, "dividend": 1, "contig_names": [], "update": 1},
                    name="func_tic_x"if x else "func_tic_y",
                    code="""
                            if(tick < 0 || tick >= genome_end)
                                return "n/a";
                            var idx = 0;
                            while(idx + 1 < contig_starts.length && contig_starts[idx + 1] <= tick)
                                idx += 1;
                            const len = contig_names[idx].length - 9;
                            if(len > 0)
                            {
                                const sec = Math.floor(Date.now() / 1000);
                                return contig_names[idx].substring(sec % len, (sec % len) + 10);
                            }
                            else
                                return contig_names[idx];
                        """)
        
        self.tick_formatter_x = get_formatter_tick()
        self.tick_formatter_x_2 = get_formatter_chr(True)
        self.tick_formatter_y = get_formatter_tick()
        self.tick_formatter_y_2 = get_formatter_chr(False)

        self.heatmap_x_axis.xaxis[0].formatter = self.tick_formatter_x
        self.heatmap_x_axis_2.xaxis[0].formatter = self.tick_formatter_x_2
        self.heatmap_y_axis.yaxis[0].formatter = self.tick_formatter_y
        self.heatmap_y_axis_2.yaxis[0].formatter = self.tick_formatter_y_2


        self.undo_button = Button(label="", css_classes=SYM_CSS + ["fa_page_previous_solid"], width=SYM_WIDTH, 
                                  height=SYM_WIDTH, sizing_mode="fixed", button_type="light", align="center")
        def undo_event():
            self.session.undo()
            self.do_config()
            self.trigger_render()
        self.undo_button.on_click(undo_event)
        self.redo_button = Button(label="", css_classes=SYM_CSS + ["fa_page_next_solid"], width=SYM_WIDTH, 
                                  height=SYM_WIDTH, sizing_mode="fixed", button_type="light", align="center")
        def redo_event():
            self.session.redo()
            self.do_config()
            self.trigger_render()
        self.redo_button.on_click(redo_event)

        self.heatmap_x_axis_2.xaxis.ticker = self.ticker_x_2
        self.heatmap_x_axis_2.xaxis.axis_line_color = None
        self.heatmap_x_axis_2.xaxis.axis_label_text_font = "monospace"
        self.heatmap_x_axis_2.xaxis.major_tick_line_color = None
        self.heatmap_x_axis_2.xaxis.major_tick_out = 0
        self.heatmap_x_axis_2.y_range.start = 1
        self.heatmap_x_axis_2.y_range.end = 2
        self.heatmap_x_axis_2.background_fill_color = None
        self.heatmap_x_axis_2.outline_line_color = None
        self.heatmap_x_axis_2.ygrid.grid_line_alpha = 0.0

        self.heatmap_y_axis_2.yaxis.ticker = self.ticker_y_2
        self.heatmap_y_axis_2.yaxis.axis_line_color = None
        self.heatmap_y_axis_2.yaxis.major_tick_line_color = None
        self.heatmap_y_axis_2.yaxis.major_tick_out = 0
        self.heatmap_y_axis_2.x_range.start = 1
        self.heatmap_y_axis_2.x_range.end = 2
        self.heatmap_y_axis_2.background_fill_color = None
        self.heatmap_y_axis_2.outline_line_color = None
        self.heatmap_y_axis_2.xgrid.grid_line_alpha = 0.0
        
        for plot in [self.heatmap, self.raw_y, self.anno_y, self.heatmap_x_axis]:
            plot.xgrid.ticker = self.ticker_x
            plot.xaxis.major_label_text_align = "left"
            plot.xaxis.ticker.min_interval = 1
        for plot in [self.heatmap, self.raw_x, self.anno_x, self.heatmap_y_axis]:
            plot.ygrid.ticker = self.ticker_y
            plot.yaxis.major_label_text_align = "right"
            plot.yaxis.ticker.min_interval = 1

        log_div = Div(text="Log:", sizing_mode="stretch_width")
        self.log_div = Div(css_classes=["scroll_y2"], width=SETTINGS_WIDTH, max_height=400, 
                            sizing_mode="stretch_height") # @todo tooltip

        self.area_range = TextInput(value="n/a", width=SETTINGS_WIDTH*2, height=26,
                                        css_classes=["tooltip", "tooltip_area_range", "text_align_center"]) 
        self.area_range.on_change("value", lambda x, y, z: self.parse_area_range())
        tools_bar = row([self.spinner, self.undo_button, self.redo_button, self.area_range, tool_bar, reset_session],
                        css_classes=["bottom_border"])
        tools_bar.height = 40
        tools_bar.min_height = 40
        tools_bar.height_policy = "fixed"
        tools_bar.align  = "center"

        _settings = self.make_tabs(tabs=[
                self.make_panel("File", children=[
                    Spacer(height=5),
                    self.make_tabs(tabs=[
                        self.make_panel("Presetting", "", [*quick_configs]),
                        self.make_panel("Export", "", [export_label, self.export_file, export_sele_layout,
                                        export_full, export_format,
                                        export_button]),
                        self.make_panel("Info", "", [version_info, log_div, self.log_div
                                                ]),
                    ])
                    ]
                ),
                self.make_panel("Normalize", children=[
                    Spacer(height=5),
                    normalization, normalization_cov,
                    self.make_tabs(tabs=[
                        #self.make_panel("Approach", "", []),
                        self.make_panel("Binominal Test", "", [rsa_l, radicl_seq_display_coverage, radicl_seq_column, radicl_seq_samples_l]),
                        self.make_panel("Dist. Dep. Dec.", "", [ddd, ddd_show, ddd_sam_l, ddd_ex_l, 
                            self.dist_dep_dec_plot
                        ]),
                        self.make_panel("Associated slices", "", [
                                                    grid_seq_samples_l, bsmcq_l, grid_seq_column, grid_seq_anno,
                                                    grid_seq_display_background, grid_seq_intersection,
                                                    grid_seq_rna_filter_l, self.ranked_columns, 
                                                    grid_seq_dna_filter_l,
                                                    self.ranked_rows, 
                                                    ]),
                        self.make_panel("ICE", "", [ice_sparse_filter]),
                    ])
                    ]
                ),
                self.make_panel("Filter", children=[
                    Spacer(height=5),
                    self.make_tabs(tabs=[
                        self.make_panel("Datapools", "", [in_group, betw_group, group_layout, ibs_l,
                                                        norm_layout
                                                    ]),
                        self.make_panel("Mapping", "", [ms_l, incomp_align_layout, multi_mapping]),
                        self.make_panel("Coordinates", "", [dds_l, x_coords, y_coords, 
                                                       symmetrie,
                                                       #,binssize not evenly dividable @todo
                                                       chrom_layout
                                                       ]),
                        self.make_panel("Annotations", "", [annos_layout,
                                                        multiple_anno_per_bin,
                                                       multiple_bin_per_anno,
                                                       ]),
                    ])]
                ),
                self.make_panel("View", children=[
                    Spacer(height=5),
                    self.make_tabs(tabs=[
                        self.make_panel("Color", "", [self.color_layout, crs_l, is_l, color_scale, color_picker, 
                                                  self.low_color, self.high_color]),
                        self.make_panel("Panels", "", [show_hide, ass_l, rss2_l, stretch, axis_lables]),
                        self.make_panel("Bins", "", [nb_l, mmbs_l, square_bins, power_ten_bin]),
                        self.make_panel("Redrawing", "", [ufs_l, rs_l, aas_l]),
                    ])]
                ),
            ]
            #css_classes=["scroll_y"]
        )
        #_settings.height = 100
        #_settings.min_height = 100
        #_settings.height_policy = "fixed"

        _settings_n_info = column([
                Spacer(height=5),
                _settings
            ]
        )
        _settings_n_info.width = SETTINGS_WIDTH + 25
        _settings_n_info.width_policy = "fixed"

        self.hidable_plots.append((_settings_n_info, ["tools"]))
        self.settings_row = row([Spacer(sizing_mode="stretch_both"), _settings_n_info, self.reshow_settings()], 
                                 css_classes=["options_panel"])
        self.settings_row.height = 100
        self.settings_row.min_height = 100
        self.settings_row.height_policy = "fixed"
        self.settings_row.width = SETTINGS_WIDTH + 25
        self.settings_row.width_policy = "fixed"

        quit_ti = TextInput(value="keepalive", name="quit_ti", visible=False)
        def close_server(x, y, z):
            print("closing server since session exited")
            sys.exit()
        quit_ti.on_change("value", close_server)

        active_tools_ti = TextInput(value="", name="active_tools_ti", visible=False)
        active_tools_ti.on_change("value", lambda x, y, z: self.save_tools(active_tools_ti.value))
        self.set_active_tools_ti = TextInput(value="", name="set_active_tools_ti", visible=False)

        communication = row([quit_ti, active_tools_ti, self.set_active_tools_ti])
        communication.visible = False

        grid_layout = [
            [self.heatmap_y_axis_2, self.heatmap_y_axis, self.anno_x,   self.raw_x,
                      None,              self.heatmap,   self.settings_row],
            [None, None,              self.anno_x_axis, self.raw_x_axis,
                      None,              None,               None],
            [None, None,              None,             None,           
                self.raw_y_axis,   self.raw_y,         None],
            [None, None,              None,             None,       
                self.anno_y_axis,  self.anno_y,        None],
            [None, None,       None,             None,           
                None,            self.heatmap_x_axis, None],
            [communication, None,       None,             None,           
                None,            self.heatmap_x_axis_2, None],
        ]

        root_min_one = grid(grid_layout, sizing_mode="stretch_both")
        root_min_one.align = "center"
        self.root = grid([[tools_bar], [root_min_one], [status_bar_row]])
        self.update_visibility()

    # overlap of the given areas relative to the larger area
    @staticmethod
    def area_overlap(a, b):
        a_xs, a_ys, a_xe, a_ye = a
        a_a = (a_xe - a_xs) * (a_ye - a_ys)
        b_xs, b_ys, b_xe, b_ye = b
        b_a = (b_xe - b_xs) * (b_ye - b_ys)

        # get interseciton
        i_xe = min(a_xe, b_xe)
        i_ye = min(a_ye, b_ye)
        i_xs = max(a_xs, b_xs)
        i_ys = max(a_ys, b_ys)
        i_a = (i_xe - i_xs) * (i_ye - i_ys)

        return i_a / max(b_a, a_a)

    @staticmethod
    def area_outside(last, curr):
        a_xs, a_ys, a_xe, a_ye = last
        b_xs, b_ys, b_xe, b_ye = curr

        return b_xs < a_xs or b_ys < a_ys or b_xe > a_xe or b_ye > a_ye

    def print(self, s):
        print(s)
        self.log_div_text += s.replace("\n", "<br>") + "<br>"
        #self.log_div_text = self.log_div_text[-5000:]

    def update_log_div(self):
        def callback():
            self.log_div.text = self.log_div_text
        self.curdoc.add_next_tick_callback(callback)

    def print_status(self, s):
        self.print(s)
        def callback():
            self.info_status_bar.text = s.replace("\n", " | ")
        self.curdoc.add_next_tick_callback(callback)


    def make_anno_str(self, s, e):
        anno_str = ""
        if "Include Annotation" in self.session.get_value(["settings", "export", "selection"]):
            for anno in self.displayed_annos:
                c = self.meta.annotations[anno].count(s, e)
                if c > 0 and c <= 10:
                    if len(anno_str) > 0:
                        anno_str += "; "
                    anno_str += anno + ": {" + self.meta.annotations[anno].info(s, e).replace("\n", " ") + "}"
                elif c > 0:
                    if len(anno_str) > 0:
                        anno_str += "; "
                    anno_str += str(c) + "x " + anno
        return anno_str

    @gen.coroutine
    @without_document_lock
    def render(self, zoom_in_render):
        def unlocked_task():
            def cancelable_task():
                    
                def callback():
                    self.spinner.css_classes = ["fade-in"]
                self.curdoc.add_next_tick_callback(callback)

                start_time = datetime.now()
                self.session.update_cds()

                d_heatmap = self.session.get_heatmap()

                raw_data_x = self.session.get_tracks(False)
                raw_data_y = self.session.get_tracks(True)
                min_max_tracks_x = self.session.get_min_max_tracks(False)
                min_max_tracks_y = self.session.get_min_max_tracks(True)

                d_anno_x = self.session.get_annotation(False)
                d_anno_y = self.session.get_annotation(True)
                displayed_annos_x = self.session.get_displayed_annos(False)
                if len(displayed_annos_x) == 0:
                    displayed_annos_x.append("")
                displayed_annos_y = self.session.get_displayed_annos(True)
                if len(displayed_annos_y) == 0:
                    displayed_annos_y.append("")

                b_col = self.session.get_background_color()

                render_area = self.session.get_drawing_area()

                canvas_size_x, canvas_size_y = self.session.get_canvas_size()
                tick_list_x = self.session.get_tick_list(True)
                tick_list_y = self.session.get_tick_list(False)
                tick_list_x_2 = self.session.get_tick_list_2(True)
                tick_list_y_2 = self.session.get_tick_list_2(False)
                ticks_x = self.session.get_ticks(True)
                ticks_y = self.session.get_ticks(False)
                ticks_x["update"] = 0
                ticks_y["update"] = 0

                palette = self.session.get_palette()
                palette_ticks = self.session.get_palette_ticks()

                w_bin, h_bin = self.session.get_bin_size()

                ranked_slice_x = self.session.get_ranked_slices(False)
                ranked_slice_y = self.session.get_ranked_slices(True)
                if self.session.get_value(["settings", "normalization", "ddd_show"]):
                    dist_dep_dec_plot_data = self.session.get_decay()
                else:
                    dist_dep_dec_plot_data = {
                            "chr": [],
                            "color": [],
                            "xs": [],
                            "ys": []
                        }

                error = self.session.get_error()
                error_text = ("None" if len(error) == 0 else error.replace("\n", "; "))
                end_time = datetime.now()

                @gen.coroutine
                def callback():
                    self.curdoc.hold()
                    self.print("ERROR: " + error_text)
                    self.color_layout.children = [self.make_color_figure(palette, palette_ticks)]
                    def mmax(*args):
                        m = 0
                        for x in args:
                            if not x is None and x > m:
                                m = x
                        return m
                    def mmin(*args):
                        m = 0
                        for x in args:
                            if not x is None and x < m:
                                m = x
                        return m

                    def readable_display(l):
                        def add_commas(x):
                            return "{:,}".format(x)
                        if l % 1000000 == 0:
                            return str(add_commas(l // 1000000)) + "mbp"
                        elif l % 1000 == 0:
                            return str(add_commas(l // 1000)) + "kbp"
                        else:
                            return str(add_commas(l)) + "bp"

                    end_text = "Rendering Done.\nCurrent Bin Size: " + readable_display(w_bin) + \
                                " x " + readable_display(h_bin) + ".\nRuntime: " + str(end_time - start_time) + \
                                ".\nDisplaying " + str(len(d_heatmap["color"])) + " bins."


                    self.raw_x_axis.xaxis.bounds = (min_max_tracks_x[0], min_max_tracks_x[1])
                    self.raw_y_axis.yaxis.bounds = (min_max_tracks_y[0], min_max_tracks_y[1])

                    def set_bounds(plot, left=None, right=None, top=None, bottom=None, color=None):
                        ra = self.plot_render_area(plot)
                        ra.left = render_area[0] if left is None else left
                        ra.bottom = render_area[1] if bottom is None else bottom
                        ra.right = render_area[2] if right is None else right
                        ra.top = render_area[3] if top is None else top
                        if not color is None:
                            ra.fill_color = color

                    set_bounds(self.raw_x, left=min_max_tracks_x[0], right=min_max_tracks_x[1])
                    set_bounds(self.raw_y, bottom=min_max_tracks_y[0], top=min_max_tracks_y[1])
                    set_bounds(self.anno_x, left=0, right=len(displayed_annos_x))
                    set_bounds(self.anno_y, bottom=0, top=len(displayed_annos_y))

                    set_bounds(self.heatmap, color=b_col)

                    self.heatmap_data.data = d_heatmap
                    self.raw_data_x.data = raw_data_x
                    self.raw_data_y.data = raw_data_y
                    
                    self.anno_x.x_range.factors = displayed_annos_x
                    self.anno_y.y_range.factors = displayed_annos_y[::-1]

                    self.anno_x_data.data = d_anno_x
                    self.anno_y_data.data = d_anno_y

                    self.heatmap.x_range.reset_start = 0
                    self.heatmap.x_range.reset_end = canvas_size_x
                    self.heatmap.y_range.reset_start = 0
                    self.heatmap.y_range.reset_end = canvas_size_y

                    self.ticker_x.extra_ticks = tick_list_x
                    self.ticker_x_2.extra_ticks = tick_list_x_2
                    self.ticker_y.extra_ticks = tick_list_y
                    self.ticker_y_2.extra_ticks = tick_list_y_2

                    self.tick_formatter_x.args = ticks_x
                    self.tick_formatter_x_2.args = ticks_x
                    self.tick_formatter_y.args = ticks_y
                    self.tick_formatter_y_2.args = ticks_y

                    self.ranked_columns_data.data = ranked_slice_y
                    self.ranked_rows_data.data = ranked_slice_x
                    self.dist_dep_dec_plot_data.data = dist_dep_dec_plot_data

                    if len(error) > 0:
                        self.heatmap.border_fill_color = "red"
                    else:
                        self.heatmap.border_fill_color = None
                    
                    self.set_area_range()

                    for plot in [self.heatmap, self.raw_y, self.anno_y, self.heatmap_x_axis]:
                        plot.xgrid.bounds = (0, canvas_size_x)
                        plot.xaxis.bounds = (0, canvas_size_x)
                    for plot in [self.heatmap, self.raw_x, self.anno_x, self.heatmap_y_axis]:
                        plot.ygrid.bounds = (0, canvas_size_y)
                        plot.yaxis.bounds = (0, canvas_size_y)

                    self.curdoc.unhold()
                    self.print_status(end_text + " | Errors: " + error_text)
                    self.curdoc.add_timeout_callback(
                        lambda: self.render_callback(),
                            self.session.get_value(["settings", "interface", "update_freq", "val"])*1000)

                self.curdoc.add_next_tick_callback(callback)
                return True
            while cancelable_task() is None:
                pass
            def callback():
                self.spinner.css_classes = ["fade-out"]
                self.session.save_session()
            self.curdoc.add_next_tick_callback(callback)

        self.undo_button.disabled = not self.session.has_undo()
        self.undo_button.css_classes = ["other_button", "fa_page_previous" if self.undo_button.disabled else "fa_page_previous_solid"]
        self.redo_button.disabled = not self.session.has_redo()
        self.redo_button.css_classes = ["other_button", "fa_page_next" if self.redo_button.disabled else "fa_page_next_solid"]
        yield executor.submit(unlocked_task)

    def trigger_render(self):
        self.session.cancel()
        self.force_render = True

    def render_callback(self):
        if self.do_render:
            self.update_log_div()
            if not self.session is None:
                if not None in (self.heatmap.x_range.start, self.heatmap.x_range.end, self.heatmap.y_range.start,
                                self.heatmap.y_range.end):

                    curr_area = (self.heatmap.x_range.start, self.heatmap.y_range.start,
                                self.heatmap.x_range.end, self.heatmap.y_range.end)
                    curr_area_size = (curr_area[2] - curr_area[0]) * (curr_area[3] - curr_area[1])
                    min_change = 1-self.session.get_value(["settings", "interface", "zoom_redraw", "val"])/100
                    zoom_in_render = False
                    if curr_area_size / self.curr_area_size < min_change or self.force_render or \
                            MainLayout.area_outside(self.last_drawing_area, curr_area):
                        if curr_area_size / self.curr_area_size < min_change:
                            self.print_status("rendering due to zoom in.")
                            zoom_in_render = True
                        elif self.force_render:
                            self.print_status("rendering due parameter change.")
                        elif MainLayout.area_outside(self.last_drawing_area, curr_area):
                            self.print_status("rendering due pan or zoom out.")
                        else:
                            self.print_status("rendering.")
                        self.force_render = False
                        self.curr_area_size = curr_area_size

                        area_dict = {
                            "x_start": curr_area[0],
                            "x_end": curr_area[2],
                            "y_start": curr_area[1],
                            "y_end": curr_area[3],
                        }
                        self.session.set_value(["area"], area_dict)

                        self.session.cancel()

                        def callback():
                            self.last_drawing_area = self.session.get_drawing_area()
                            self.render(zoom_in_render)
                        self.curdoc.add_next_tick_callback(callback)
                        return
                    else:
                        self.set_area_range()

                self.curdoc.add_timeout_callback(
                    lambda: self.render_callback(), self.session.get_value(["settings", "interface", "update_freq", "val"])*1000)
            else:
                self.curdoc.add_timeout_callback(lambda: self.render_callback(), 1000)

    def set_root(self):
        self.curdoc.clear()
        self.curdoc.add_root(self.root)
        self.curdoc.title = "Smoother"
        self.do_render = True
        self.force_render = True
        self.do_config()
        self.render_callback()

