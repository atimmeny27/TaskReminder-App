# <editor-fold desc=" Setup and Imports">
import os
os.environ['KIVY_WINDOW'] = 'sdl2'
os.environ['SDL_VIDEO_CENTERED'] = '1'
import sqlite3
from kivy.config import Config
Config.set('graphics', 'width', '1200')
Config.set('graphics', 'height', '800')
Config.set('graphics', 'resizable', '0')  # disable resizing
# Kivy UI stuff
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, Rectangle, Line, Ellipse
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.image import Image
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.slider import Slider
from kivy.uix.behaviors import DragBehavior
from kivy.uix.colorpicker import ColorPicker
from kivy.animation import Animation
from kivy.properties import NumericProperty
from kivy.uix.spinner import Spinner

# Standard libraries
import time
import subprocess
from datetime import datetime
from calendar import monthrange
from typing import List, Tuple, Union

Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

DB_PATH = os.path.join(os.path.dirname(__file__), "reminders.db")
# </editor-fold>

def send_mac_notification(title, message):
    """Send a native macOS notification using osascript."""
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script])

# SQL Database Setup
def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Create base tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        image_path TEXT DEFAULT '',
        folder_order INTEGER DEFAULT 0
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        folder_name TEXT NOT NULL,
        reminder_order INTEGER DEFAULT 0,
        urgency_level INTEGER DEFAULT 3,
        FOREIGN KEY (folder_name) REFERENCES folders(name)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reminder_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reminder_text TEXT NOT NULL,
        folder_name TEXT NOT NULL,
        notify_at TEXT NOT NULL,
        FOREIGN KEY (folder_name) REFERENCES folders(name)
    )
    ''')

    # 2. Now alter the table to add notify_at
    try:
        cursor.execute("ALTER TABLE reminders ADD COLUMN notify_at TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # 3. Themes table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS themes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        background TEXT,
        "primary" TEXT,
        "secondary" TEXT,
        "text" TEXT
    )
    ''')

    # Step 1: Add selected_theme column to track the currently selected theme
    try:
        cursor.execute("ALTER TABLE themes ADD COLUMN selected_theme INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        # If column already exists
        pass

    # 4. Only insert Tropical if NO themes exist (it is a default created but deletable third theme)
    cursor.execute("SELECT COUNT(*) FROM themes")
    theme_count = cursor.fetchone()[0]
    if theme_count == 0:
        cursor.execute("""
            INSERT INTO themes (name, background, "primary", "secondary", "text")
            VALUES (?, ?, ?, ?, ?)
        """, (
            "Tropical",
            "#ffe8b0",  # sand colors
            "#ffa07a",  # light coral (primary)
            "#20b2aa",  # light sea green (secondary)
            "#000000"   # black text
        ))

    # 5. Folder setup
    cursor.execute("INSERT OR IGNORE INTO folders (name) VALUES ('Pinned'), ('Recurring'), ('Completed'), ('Non-Completed')")
    cursor.execute("UPDATE folders SET folder_order = 0 WHERE name = 'Pinned'")
    cursor.execute("UPDATE folders SET folder_order = 1 WHERE name = 'Recurring'")
    cursor.execute("UPDATE folders SET folder_order = 2 WHERE name = 'Non-Completed'")
    cursor.execute("UPDATE folders SET folder_order = 3 WHERE name = 'Completed'")

    cursor.execute("""
        SELECT name FROM folders
        WHERE name NOT IN ('Pinned', 'Recurring', 'Non-Completed', 'Completed')
        ORDER BY name
    """)

    other_folders = cursor.fetchall()
    for i, (name,) in enumerate(other_folders, start=4):
        cursor.execute("UPDATE folders SET folder_order = ? WHERE name = ?", (i, name))

    conn.commit()
    conn.close()

class DraggableFolder(RelativeLayout):
    def __init__(self, folder_name, icon_path, app_ref, **kwargs):
        super().__init__(size_hint_y=None, height=Window.height * 0.075, **kwargs)  # Kivy widgets are easier to use when called in a constructor

        self.folder_name = folder_name
        self.app_ref = app_ref
        self.dragging = False

        layout = BoxLayout(
            orientation='horizontal',
            spacing=Window.width * 0.01,  # 1% of width
            padding=(Window.width * 0.01, Window.height * 0.01)  # 1% padding
        )

        if icon_path:
            icon = Image(
                source=icon_path,
                size_hint=(None, 1),
                width=Window.width * 0.032  # 3% of width
            )
            layout.add_widget(icon)

        self.label = HoverButton(
            text=f"[b]{folder_name}[/b]",
            markup=True,
            background_normal='',
            app_ref=self.app_ref
        )

        layout.add_widget(self.label)
        self.add_widget(layout)

        Window.bind(mouse_pos=self.check_drag)

    def check_drag(self, window, pos):
        if self.dragging:
            self.center_y = pos[1]

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.dragging = True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.dragging:
            self.dragging = False

            parent = self.parent
            if not parent:
                return super().on_touch_up(touch)

            # Get all draggable folders
            draggable_folders = [w for w in parent.children if isinstance(w, DraggableFolder)]
            draggable_folders.reverse()  # Top to bottom visual order

            if self in draggable_folders:
                draggable_folders.remove(self)

            # Convert touch to local coordinates for each widget
            insertion_index = len(draggable_folders)
            for i, widget in enumerate(draggable_folders):
                local_pos = widget.to_widget(*touch.pos)
                if widget.collide_point(*local_pos):
                    insertion_index = i + 1  # Drop *below* the one being hovered
                    break

            draggable_folders.insert(insertion_index, self)

            # Add back non-draggable folders
            non_draggables = [w for w in parent.children if not isinstance(w, DraggableFolder)]

            # Combine and sort by y (top to bottom)
            all_widgets = draggable_folders + non_draggables
            all_widgets.sort(key=lambda w: w.y, reverse=True)

            parent.clear_widgets()
            for widget in all_widgets:
                parent.add_widget(widget)

            self.app_ref.reorder_folders()

        return super().on_touch_up(touch)

class HoverButton(Button):
    def __init__(self, app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref

        # Use theme colors if available
        if self.app_ref:
            self.default_color = self.app_ref.theme["primary"]
            self.hover_color = self.app_ref.theme["secondary"]
        else:
            # Fallback to hardcoded colors
            self.default_color = (0.239, 0.059, 0.349, 1)
            self.hover_color = (0.086, 0.616, 0.651, 1)

        self.background_normal = ''
        self.background_color = self.default_color

        # Add this to set the label text color
        if self.app_ref and hasattr(self.app_ref, "theme"):
            self.color = self.app_ref.theme["text"]
        else:
            self.color = (1, 1, 1, 1)  # fallback to white

        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, *args):
        if not self.get_root_window():
            return  # Widget not in the UI yet

        pos = args[1]
        if any(isinstance(w, Popup) and w._window is not None for w in Window.children):
            return

        inside = self.collide_point(*self.to_widget(*pos))
        self.background_color = self.hover_color if inside else self.default_color

class FlickScrollView(ScrollView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.velocity = 0
        self.last_scroll_time = time.time()
        self._anim = None

    def on_touch_scroll(self, touch, check_children=True):
        if 'button' in touch.profile and touch.button in ('scrollup', 'scrolldown'):
            now = time.time()
            delta_time = now - self.last_scroll_time
            direction = 1 if touch.button == 'scrollup' else -1
            self.last_scroll_time = now

            # Calculate a simulated velocity based on time between events
            step = 0.04  # base scroll size
            if delta_time < 0.1:
                self.velocity += step * direction * 7  # fast scroll adds momentum
            else:
                self.velocity += step * direction

            if self._anim:
                self._anim.cancel(self)
            self.start_flick()

            return True
        return super().on_touch_scroll(touch, check_children)

    def start_flick(self):
        def flick(dt):
            self.scroll_y += self.velocity
            self.scroll_y = max(0.0, min(1.0, self.scroll_y))
            self.velocity *= 0.02  # friction for scrolling

            if abs(self.velocity) < 0.001:
                return False
        Clock.schedule_interval(flick, 1 / 60.)

class CircleButton(Button):
    def __init__(self, app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref

        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0, 0, 0, 0)  # Fully transparent center
        self.is_hovered = False

        with self.canvas.before:
            self.fill_color = Color(0, 0, 0, 1)
            self.fill_circle = Ellipse(pos=self.pos, size=self.size)

            self.stroke_color = Color(1, 1, 1, 1)
            stroke_width = Window.width * 0.002
            self.stroke_circle = Line(circle=(self.center_x, self.center_y, self.width / 2), width=stroke_width)

        self.bind(pos=self.update_graphics, size=self.update_graphics)
        Window.bind(mouse_pos=self.on_mouse_pos)

        # Initial graphics
        Clock.schedule_once(lambda dt: self.update_graphics(), 0)

    def on_mouse_pos(self, *args):
        if not self.get_root_window():
            return
        pos = args[1]
        inside = self.collide_point(*self.to_widget(*pos))
        if self.is_hovered != inside:
            self.is_hovered = inside
            self.update_graphics()

    def update_graphics(self, *args):
        if not self.app_ref or not hasattr(self.app_ref, "theme"):
            return

        theme = self.app_ref.theme

        self.fill_color.rgba = theme["background"]
        self.stroke_color.rgba = theme["primary"] if self.is_hovered else theme["secondary"]

        self.fill_circle.pos = self.pos
        self.fill_circle.size = self.size

        self.stroke_circle.circle = (
            self.center_x, self.center_y,
            min(self.width, self.height) / 2 - Window.width * 0.001
        )

class FolderButton(RelativeLayout):
    def __init__(self, text, icon_path=None, app_ref=None, **kwargs):
        super().__init__(size_hint_y=None, height=Window.height * 0.075, **kwargs)

        layout = BoxLayout(
            orientation='horizontal',
            spacing=Window.width * 0.01,
            padding=(Window.width * 0.01, Window.height * 0.01)
        )

        if icon_path:
            icon = Image(
                source=icon_path,
                size_hint=(None, 1),
                width=Window.width * 0.032
            )
            layout.add_widget(icon)

        label = HoverButton(
            app_ref=app_ref,
            text=f"[b]{text}[/b]",
            markup=True,
            background_normal=''
        )
        self.label = label
        layout.add_widget(label)
        self.add_widget(layout)

class CalendarCell(Button):
    def __init__(self, day, calendar_ref, **kwargs):
        super().__init__(**kwargs)
        self.day = day
        self.calendar_ref = calendar_ref  # store a reference to CalendarGrid
        self.text = str(day)
        self.size_hint = (None, None)
        self.size = (100, 70)
        self.markup = True
        self.background_normal = ''
        self.color = (0, 0, 0, 1)

        # Default background
        self.update_background()

        # Clicking the cell
        self.bind(on_press=self.toggle_selection)

    def update_background(self):
        today = (self.calendar_ref.current_year, self.calendar_ref.current_month, self.day)
        if today in self.calendar_ref.selected_dates:
            self.background_color = (0.7, 0.7, 0.7, 1)  # Highlighted color
        else:
            self.background_color = (0.91, 0.902, 0.875, 1)  # Normal white color

    def toggle_selection(self, *args):
        today = (self.calendar_ref.current_year, self.calendar_ref.current_month, self.day)
        if today in self.calendar_ref.selected_dates:
            self.calendar_ref.selected_dates.remove(today)
        else:
            self.calendar_ref.selected_dates.append(today)
        self.update_background()

class CalendarGrid(ScrollView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_dates = set()  # Store selected dates (format "YYYY-MM-DD")
        self.grid = GridLayout(
            cols=7,
            size_hint=(None, None),
            width=700,
            row_default_height=70,
            row_force_default=True
        )
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.add_widget(self.grid)
        self.time_label = Label(text="Current Time: --")  # Added to stay compatible
        self.build_calendar()

    def build_calendar(self, year=None, month=None):
        self.grid.clear_widgets()

        now = datetime.now()
        year = year or now.year
        month = month or now.month
        days_in_month = monthrange(year, month)[1]

        # Weekday headers
        weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        for day in weekdays:
            lbl = Label(
                text=f"[b]{day}[/b]",
                markup=True,
                size_hint=(None, None),
                size=(100, 50),
                color=(0, 0, 0, 1)
            )
            self.grid.add_widget(lbl)

        # Blank space until the first day
        first_day = (datetime(year, month, 1).weekday() + 1) % 7
        for _ in range(first_day):
            self.grid.add_widget(Label(size_hint=(None, None), size=(100, 70)))

        # Dates
        for day in range(1, days_in_month + 1):
            full_date = f"{year}-{month:02d}-{day:02d}"

            btn = Button(
                text=str(day),
                size_hint=(None, None),
                size=(100, 70),
                background_normal='',
                background_color=(0.91, 0.902, 0.875, 1),
                color=(0, 0, 0, 1)
            )

            if full_date in self.selected_dates:
                btn.background_color = (0.6, 0.8, 1, 1)  # Light blue if selected day

            btn.bind(on_press=lambda instance, date=full_date: self.toggle_date(instance, date))
            self.grid.add_widget(btn)

    def toggle_date(self, btn, date_str):
        if date_str in self.selected_dates:
            self.selected_dates.remove(date_str)
            btn.background_color = (0.91, 0.902, 0.875, 1)  # Back to white
        else:
            self.selected_dates.add(date_str)
            btn.background_color = (0.6, 0.8, 1, 1)  # Selected color

    def update_time_label(self, dt):
        now = datetime.now()
        self.time_label.text = f"[color=000000][b]Current Time: {now.strftime('%I:%M:%S %p')}[/b][/color]"
        self.time_label.markup = True

class DraggableReminder(BoxLayout):
    def __init__(self, reminder_text, urgency_level, folder_name, app_ref, notify_at=None, **kwargs):
        super().__init__(orientation='horizontal',
                         size_hint=(None, None),
                         size=(Window.width * 0.5, Window.height * 0.065),
                         spacing=Window.width * 0.0083,
                         padding=(Window.width * 0.0042, Window.height * 0.00625),
                         **kwargs)

        self.app_ref = app_ref
        self.reminder_text = reminder_text
        self.folder_name = folder_name
        self.dragging = False
        self.notify_at = [notify_at] if isinstance(notify_at, str) else (notify_at or [])

        # Complete Button
        btn_wrapper = FloatLayout(size_hint=(None, 1), width=Window.width * 0.025)
        self.complete_btn = CircleButton(
            app_ref=self.app_ref,
            size_hint=(None, None),
            size=(Window.width * 0.02, Window.width * 0.02),
            pos_hint={'center_x': 0.5, 'center_y': 0.52}
        )
        self.complete_btn.bind(on_press=lambda instance: self.app_ref.mark_as_completed(reminder_text, folder_name))
        btn_wrapper.add_widget(self.complete_btn)
        self.add_widget(btn_wrapper)

        # Calendar Button (only if not in Completed folder)
        if self.folder_name != "Completed":
            calendar_wrapper = FloatLayout(size_hint=(None, 1), width=Window.width * 0.025)
            calendar_btn = Button(
                size_hint=(None, None),
                size=(Window.width * 0.06, Window.width * 0.06),
                background_normal='Images for App/calendar.png',
                background_down='Images for App/calendar.png',
                pos_hint={'center_x': 0.5, 'center_y': 0.52},
                background_color=(1, 1, 1, 1)
            )
            calendar_btn.bind(on_press=self.open_calendar_popup)
            calendar_wrapper.add_widget(calendar_btn)
            self.add_widget(calendar_wrapper)

        # Urgency Level
        if urgency_level == 2:
            self.urgency_image = Image(
                source='Images for App/lvl1.png',
                size_hint=(None, 1),
                width=Window.width * 0.025
            )
            self.add_widget(self.urgency_image)
        elif urgency_level == 3:
            self.urgency_image = Image(
                source='Images for App/lvl2.png',
                size_hint=(None, 1),
                width=Window.width * 0.025
            )
            self.add_widget(self.urgency_image)

        # Text Button
        self.text_btn = HoverButton(
            text=reminder_text,
            size_hint=(1, 1),
            background_normal='',
            background_color=self.app_ref.theme.get("primary", (0.5, 0.5, 0.5, 1)),
            app_ref=self.app_ref
        )
        self.text_btn.color = self.app_ref.theme.get("text", (1, 1, 1, 1))

        # Info box container
        info_box = BoxLayout(orientation='vertical', size_hint=(1, 1))
        info_box.add_widget(self.text_btn)

        # Display up to 2 dates horizontally, then "+X more"
        notify_dates = self.notify_at[:2]
        extra_count = max(0, len(self.notify_at) - 2)

        date_layout = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=None, height=25)

        for date_str in notify_dates:
            try:
                dt = datetime.fromisoformat(date_str)
                formatted_time = dt.strftime("%b %d, %Y at %I:%M %p")
                is_overdue = dt < datetime.now()
                text_color = (1, 0.3, 0.3, 1) if is_overdue else self.app_ref.theme["text"]

                label = Label(
                    text=f"[size=25][b][i]{formatted_time}[/i][/b][/size]",
                    markup=True,
                    size_hint=(None, 1),
                    width=300,
                    color=text_color
                )
                label.bind(size=label.setter('text_size'))

                if is_overdue:
                    self.text_btn.color = text_color

                date_layout.add_widget(label)
            except Exception as e:
                print(f"Invalid date format in notify_at: {date_str} -> {e}")

        if extra_count > 0:
            more_label = Label(
                text=f"[size=25][b][i]+{extra_count} more[/i][/b][/size]",
                markup=True,
                size_hint=(None, 1),
                width=220,
                color=self.app_ref.theme["text"]
            )
            more_label.bind(size=more_label.setter('text_size'))
            date_layout.add_widget(more_label)

        info_box.add_widget(date_layout)

        self.add_widget(info_box)

    def update_bg_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

        # Make draggable
        Window.bind(mouse_pos=self.check_drag)

    def open_calendar_popup(self, instance):
        layout = FloatLayout()

        # Month sidebar (left)
        month_sidebar = BoxLayout(
            orientation='vertical',
            spacing=5,
            size_hint=(None, None),
            size=(120, 500),
            pos_hint={"x": 0.05, "center_y": 0.376}
        )

        self.month_buttons = [] # Blank list

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        for index, month in enumerate(month_names):
            month_btn = Button(
                text=f"[b]{month}[/b]",
                markup=True,
                color=(0, 0, 0, 1),
                size_hint=(1, None),
                height=38,
                halign='center',
                valign='middle',
                background_normal='',
                background_color=(0.91, 0.902, 0.875, 1)  # White background
            )
            month_btn.bind(size=month_btn.setter('text_size'))

            # Save to month_buttons list
            self.month_buttons.append(month_btn)

            # Bind button to selection
            month_btn.bind(on_press=lambda instance, idx=index: self.select_month(idx))

            month_sidebar.add_widget(month_btn)

        layout.add_widget(month_sidebar)

        # Calendar grid (center)
        self.calendar = CalendarGrid(
            size_hint=(None, None),
            size=(700, 500),
            pos_hint={"center_x": 0.55, "center_y": 0.41}
        )
        self.calendar.time_label.font_size = 40

        # Weekday background
        weekday_bg = FloatLayout(
            size_hint=(None, None),
            size=(715, 50),
            pos_hint={"center_x": 0.547, "center_y": 0.715}
        )

        with weekday_bg.canvas.before:
            Color(0.91, 0.902, 0.875, 1)
            self.weekday_bg_rect = Rectangle(pos=weekday_bg.pos, size=weekday_bg.size)

        with weekday_bg.canvas.after:
            Color(0, 0, 0, 1)
            self.weekday_border = Line(rectangle=(weekday_bg.x, weekday_bg.y, weekday_bg.width, weekday_bg.height),
                                       width=3)

        def update_weekday_rects(*args):
            self.weekday_bg_rect.pos = weekday_bg.pos
            self.weekday_bg_rect.size = weekday_bg.size
            self.weekday_border.rectangle = (*weekday_bg.pos, *weekday_bg.size)

        weekday_bg.bind(pos=update_weekday_rects, size=update_weekday_rects)

        layout.add_widget(weekday_bg)
        layout.add_widget(self.calendar)

        # Time label box (bottom)
        time_box = FloatLayout(
            size_hint=(None, None),
            size=(820, 60),
            pos_hint={"center_x": 0.58, "y": 0.012}
        )

        with time_box.canvas.before:
            Color(0.91, 0.902, 0.875, 1)
            self.time_bg_rect = Rectangle(pos=time_box.pos, size=time_box.size)

        time_box.bind(pos=lambda inst, val: setattr(self.time_bg_rect, 'pos', val))
        time_box.bind(size=lambda inst, val: setattr(self.time_bg_rect, 'size', val))

        self.calendar.time_label.pos_hint = {"center_x": 0.5, "center_y": 0.5}
        time_box.add_widget(self.calendar.time_label)
        layout.add_widget(time_box)

        Clock.schedule_interval(self.calendar.update_time_label, 1)

        # Year Dropdown (top right)
        current_year = datetime.now().year
        years = [str(current_year + i) for i in range(6)]  # current year + 5 years ahead

        self.year_spinner = Spinner(
            text=f"[b]{current_year}[/b]",
            markup=True,
            values=[str(current_year + i) for i in range(6)],
            size_hint=(None, None),
            size=(170, 70),
            pos_hint={"center_x": 0.85, "center_y": 0.9},
            background_normal='',
            background_color=(0.91, 0.902, 0.875, 1),
            color=(0, 0, 0, 1)
        )

        def on_year_select(spinner, selected_year):
            selected_year = int(selected_year)
            self.calendar.build_calendar(year=selected_year)

        self.year_spinner.bind(text=self.on_year_select)
        layout.add_widget(self.year_spinner)

        popup = Popup(
            title="Select Dates",
            content=layout,
            size_hint=(None, None),
            size=(1100, 800)
        )

        save_btn = Button(
            text='[b]Save Date[/b]',
            markup=True,
            size_hint=(None, None),
            size=(200, 60),  # Pixel-based size
            pos_hint={"center_x": 0.872, "y": 0.13},
            background_normal='',
            background_color=(0.91, 0.902, 0.875, 1),  # White color
            color=(0, 0, 0, 1)  # Black text for contrast
        )

        self.schedule_spinner = Spinner(
            text="Set Schedule",
            values=["Daily", "Weekly", "Monthly", "Quarterly"],
            size_hint=(None, None),
            size=(220, 50),
            pos_hint={"center_x": 0.15, "center_y": 0.9},
            background_normal='',
            background_color=(0.91, 0.902, 0.875, 1),
            color=(0, 0, 0, 1)
        )
        layout.add_widget(self.schedule_spinner)

        def save_selected_date(instance):
            if not self.calendar.selected_dates:
                return  # Maybe add warning popup later

            selected = list(self.calendar.selected_dates)[0]  # Take the first selected date
            year, month, day = map(int, selected.split('-'))

            # Pull the original notify_at time
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT notify_at FROM reminders
                WHERE text = ? AND folder_name = ?
            """, (self.reminder_text, self.folder_name))
            row = cursor.fetchone()
            conn.close()

            hour, minute = 9, 0  # fallback default
            if row and row[0]:
                try:
                    dt = datetime.fromisoformat(row[0])
                    hour, minute = dt.hour, dt.minute
                except ValueError:
                    pass

            notify_dt = datetime(year, month, day, hour, minute)

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reminder_notifications (reminder_text, folder_name, notify_at)
                VALUES (?, ?, ?)
            """, (self.reminder_text, self.folder_name, notify_dt.isoformat()))

            conn.commit()
            conn.close()


            # Check if a recurring schedule was selected
            schedule_type = self.schedule_spinner.text.lower()
            if schedule_type in ["daily", "weekly", "monthly", "quarterly"]:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                base_dt = notify_dt
                for i in range(1, 6):  # Next 5 scheduled times
                    if schedule_type == "daily":
                        next_dt = base_dt + timedelta(days=i)
                    elif schedule_type == "weekly":
                        next_dt = base_dt + timedelta(weeks=i)
                    elif schedule_type == "monthly":
                        month = base_dt.month + i
                        year = base_dt.year + (month - 1) // 12
                        month = ((month - 1) % 12) + 1
                        day = min(base_dt.day, monthrange(year, month)[1])
                        next_dt = datetime(year, month, day, base_dt.hour, base_dt.minute)
                    elif schedule_type == "quarterly":
                        month = base_dt.month + (i * 3)
                        year = base_dt.year + (month - 1) // 12
                        month = ((month - 1) % 12) + 1
                        day = min(base_dt.day, monthrange(year, month)[1])
                        next_dt = datetime(year, month, day, base_dt.hour, base_dt.minute)
                    else:
                        continue

                    cursor.execute("""
                        INSERT INTO reminder_notifications (reminder_text, folder_name, notify_at)
                        VALUES (?, ?, ?)
                    """, (self.reminder_text, self.folder_name, next_dt.isoformat()))

                conn.commit()
                conn.close()

            popup.dismiss()

            # Calculate delay
            delay = (notify_dt - datetime.now()).total_seconds()

            if delay > 0:
                Clock.schedule_once(
                    lambda dt: send_mac_notification("Reminder", self.reminder_text),
                    delay
                )

            # Refresh UI (reload folder)
            self.app_ref.load_reminders(self.folder_name)

        save_btn.bind(on_press=save_selected_date)
        layout.add_widget(save_btn)

        popup.open()

    def update_calendar_year(self, year):
        self.calendar.clear_widgets()
        self.calendar.build_calendar(year=year)

    def on_year_select(self, spinner, selected_year):
        selected_year = int(selected_year)
        # Rebuild the calendar with new year, keep current month
        self.calendar.build_calendar(year=selected_year)

    def check_drag(self, window, pos):
        if self.dragging:
            self.center_y = pos[1]

    def select_month(self, selected_month_index):
        for idx, btn in enumerate(self.month_buttons):
            if idx == selected_month_index:
                btn.background_color = (0.7, 0.7, 0.7, 1)  # Highlighted
            else:
                btn.background_color = (0.91, 0.902, 0.875, 1)  # Normal

        # Now, rebuild calendar grid:
        selected_year = int(self.year_spinner.text.replace("[b]", "").replace("[/b]", ""))
        selected_month = selected_month_index + 1  # Because months are 1-based (January = 1)
        self.calendar.build_calendar(year=selected_year, month=selected_month)

    def highlight_selected_month(self, selected_month_index):
        for idx, btn in enumerate(self.month_buttons):
            if idx == selected_month_index:
                btn.background_color = (0.7, 0.7, 0.7, 1)  # Highlight color (gray)
            else:
                btn.background_color = (0.91, 0.902, 0.875, 1)  # Normal white

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.dragging = True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self.dragging:
            self.dragging = False

            parent = self.parent
            if not parent:
                return super().on_touch_up(touch)

            # Get all reminder widgets
            reminder_widgets = [w for w in parent.children if isinstance(w, DraggableReminder)]
            reminder_widgets.reverse()  # Top to bottom visual order

            if self in reminder_widgets:
                reminder_widgets.remove(self)

            # Find where to insert based on collision
            insertion_index = len(reminder_widgets)
            for i, widget in enumerate(reminder_widgets):
                local_pos = widget.to_widget(*touch.pos)
                if widget.collide_point(*local_pos):
                    insertion_index = i + 1
                    break

            reminder_widgets.insert(insertion_index, self)

            # Clear and re-add in new order
            parent.clear_widgets()
            for widget in reminder_widgets:
                parent.add_widget(widget)

            # Update reminder order in DB
            self.app_ref.update_reminder_order(self.folder_name, self.reminder_text, insertion_index)

        return super().on_touch_up(touch)

class RemindersApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Check if the database exists before creating it
        db_exists = os.path.exists(DB_PATH)

        # Create database if needed, works with db_exists function above
        setup_database()

        if not db_exists:
            # Temporary neutral theme before popup choice
            self.theme = {
                "background": (0.2, 0.2, 0.2, 1),
                "primary": (0.3, 0.3, 0.7, 1),
                "secondary": (0.702, 0.859, 0.816, 1),
                "text": (1, 1, 1, 1)
            }

            # Show first-time theme popup
            Clock.schedule_once(lambda dt: self.show_first_theme_popup(), 0.5)
        else:
            # Load the previously selected theme
            self.load_last_theme()

    def build(self):
        self.title = "Reminders App"

        self.root_layout = FloatLayout()

        with self.root_layout.canvas.before:
            self.bg_color = Color(*self.theme["background"])
            self.bg_rect = Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)
            self.border_color = Color(*self.theme["secondary"])
            self.full_border = Line(width=14, rectangle=(0, 0, 0, 0))

        self.main_layout = BoxLayout(orientation='horizontal', size_hint=(1, 1))
        self.root_layout.add_widget(self.main_layout)

        with self.root_layout.canvas.after:
            self.divider_color = Color(*self.theme["secondary"])
            self.divider_line_left = Line(points=[0, 0, 0, 0], width=8)  # Initial placeholder
            self.divider_line_right = Line(points=[0, 0, 0, 0], width=8)

        self.root_layout.bind(pos=self.update_layout, size=self.update_layout)
        Window.bind(size=self.update_layout)

        self.setup_ui()
        self.apply_theme()

        self.update_layout()
        Clock.schedule_once(lambda dt: self.update_layout(), 0)

        return self.root_layout

    def update_layout(self, *args):
        self.bg_rect.pos = self.root_layout.pos
        self.bg_rect.size = self.root_layout.size
        self.full_border.rectangle = (
            self.root_layout.x, self.root_layout.y,
            self.root_layout.width, self.root_layout.height
        )

        y = self.root_layout.y
        height = self.root_layout.height

        left_divider_x = Window.width * 0.19
        right_divider_x = Window.width * 0.72

        # Dynamically scale width — e.g. 0.3% of the window width
        dynamic_width = Window.width * 0.0032
        self.divider_line_left.width = dynamic_width
        self.divider_line_right.width = dynamic_width

        self.divider_line_left.points = [left_divider_x, y, left_divider_x, y + height]
        self.divider_line_right.points = [right_divider_x, y, right_divider_x, y + height]

        self.root_layout.canvas.ask_update()

    def update_full_border(self, instance, value):
        self.full_border.rectangle = (instance.x, instance.y, instance.width, instance.height)

    def update_content_border(self, instance, value):
        self.content_border.rectangle = (instance.x, instance.y, instance.width, instance.height)

    def mark_as_completed(self, reminder_text, current_folder):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. Deletes reminder from every folder, keeps in Completed
        cursor.execute("""
            DELETE FROM reminders
            WHERE text = ? AND folder_name != 'Completed'
        """, (reminder_text,))

        # 2. Insert into Completed if it's not already there
        cursor.execute("""
            SELECT 1 FROM reminders
            WHERE text = ? AND folder_name = 'Completed'
        """, (reminder_text,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO reminders (text, folder_name)
                VALUES (?, 'Completed')
            """, (reminder_text,))

        conn.commit()
        conn.close()

        # 3. Reload current folder
        self.load_reminders(current_folder)

        if current_folder != "Non-Completed":
            self.load_reminders("Non-Completed")

    def update_reminder_order(self, folder_name, moved_text, new_index):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Fetch current list of reminders
        cursor.execute("SELECT text FROM reminders WHERE folder_name = ? ORDER BY reminder_order ASC", (folder_name,))
        reminders = [row[0] for row in cursor.fetchall()]

        # Remove and reinsert the moved reminder at new index
        if moved_text in reminders:
            reminders.remove(moved_text)
            reminders.insert(new_index, moved_text)

        # Update each reminder with new order
        for i, text in enumerate(reminders):
            cursor.execute("""
                UPDATE reminders
                SET reminder_order = ?
                WHERE text = ? AND folder_name = ?
            """, (i, text, folder_name))

        conn.commit()
        conn.close()

        self.load_reminders(folder_name)

    def reorder_folders(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        priority_folders = {"Pinned", "Recurring", "Non-Completed", "Completed"}
        priority_map = {"Pinned": 0, "Recurring": 1, "Non-Completed": 2, "Completed": 3}

        # Reverse the list since Kivy StackLayout children are in reverse order
        visible_folders = [child for child in self.sidebar.children if isinstance(child, DraggableFolder)]
        visible_folders = visible_folders[::-1]

        custom_index = 4  # Start after the last system folder

        for widget in visible_folders:
            folder_name = widget.folder_name

            if folder_name in priority_folders:
                continue  # Skip protected folders

            cursor.execute("""
                UPDATE folders
                SET folder_order = ?
                WHERE name = ?
            """, (custom_index, folder_name))
            custom_index += 1

        # Re-apply hardcoded order for priority folders to ensure consistency
        for name, order in priority_map.items():
            cursor.execute("UPDATE folders SET folder_order = ? WHERE name = ?", (order, name))

        conn.commit()
        conn.close()

        self.load_folders()

    def reorder_reminders(self):
        if not self.selected_folder:
            return

        folder_clean = self.selected_folder.replace('[b]', '').replace('[/b]', '')
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Loop through widgets in their current visual order
        for index, reminder_widget in enumerate(self.reminder_list.children[::-1]):  # bottom-to-top, so reverse
            if hasattr(reminder_widget, 'reminder_text'):
                cursor.execute("""
                    UPDATE reminders
                    SET reminder_order = ?
                    WHERE text = ? AND folder_name = ?
                """, (index, reminder_widget.reminder_text, folder_clean))

        conn.commit()
        conn.close()

    def show_help_popup(self, instance):
        # Large scrollable blank popup content
        scroll = ScrollView(size_hint=(1, 1))
        content = Label(
            text='''
    [size=36][b]Reminders App Help[/b][/size]
    
    
        [size=32][b]Getting Started[/b][/size]
            
            
            - This app is designed to have a highly customizable User Interface, with 
              themes, app icons, and all the functionality of actually reminding you.
              
              
        [size=32][b]Folders[/b][/size]
        
        
            -Folders are where your reminders are stored
            
            
            - These appear on the left sidebar
            
            
            -There are [b]4 built-in[/b] folders
            
                - [b]Pinned[/b] : Put your most important reminders here
                      
                - [b]Recurring[/b] : Any reminders you select to be recurring will appear here
                
                - [b]Non-Completed[/b] : This folder will store every reminder not yet finished
                          
                - [b]Completed[/b] : This is where all finished reminders will go
                
                
            - Any added folders can be rearranged by dragging and dropping
        
        
        [size=32][b]Functions[/b][/size]
            
            
            [b]Add Folder : [/b] 
            
            This is how to add folders, you will be prompted to name the folder,
            and once you click "Add" it will be added.
            
            
            [b]Delete Folder : [/b]
            
            Click on a created folder you wish to delete, and click delete. It 
            will be removed. You cannot delete the 4 preinstalled folders.
            
            
            [b]Change Folder Icon : [/b]
            
            Select a folder and press this button. It will prompt a drag-and-drop
            for an image. You can use any image, but a .png is recommended.
            
            
            [b]Add Reminder : [/b]
            
            This is how to add reminders, the actual functionality of the app.
            Select a folder to drop it into, if you select anything other than
            the "Non-Completed" folder, it will be automatically added to it.
            
            There are [b]3 Options[/b] for reminders
                
                - [b]Add Text[/b] : This is where you can add the reminder text, this
                                       will appear in the notification.
                
                
                - [b] Urgency Level[/b] : This provides a visual cue to more urgent reminders.
                
                
                - [b]Make Recurring[/b] : This gives the ability to make a reminder repeat.
                                                   This will be added to the recurring folder if 
                                                   selected. You can choose the dates to repeat 
                                                   pressing the calendar icon once added.
                                        
                
                - [b]Date and Time[/b] : This is where to select the date and time of the reminder.
            
            
            
            
            [b]Change Theme : [/b]
            
            This is where the user customization happens. There are 2 presets, light mode
            and dark mode. There is also a 3rd option, "Tropical", this is a deletable
            custom preset. To delete any theme, just hit the "X" to the right of the name. 
            
            To make your own, click "custom colors", then go through and either use the 
            color wheel, or insert a hex value. Then click back, and "save theme". Give it 
            a name, and it will be added to your list of pre-saved themes. All selected 
            themes will persist across opening / closing the app.
            
            
            
        [size=32][b]Main Section[/b][/size]
            
            - To complete any reminder, click the little circle to the left of it. It will be 
                removed from all folders including non-completed, pinned, or recurring and 
                moved into completed.
            
            - To set repeating dates, click the calendar icon in between the reminder and 
               complete button. You can select a pre-made schedule of daily, weekly, monthly, 
               or quarterly. You can also select any day or days up to 5 years away by selecting your 
               year, month, and days. Click "Save Date(s)" and they will be added to your reminders.
        
        
        [size=32][b]For any questions, improvements, or complaints, please leave an app store 
          comment. Thank You[/b][/size]
            
        
            ''',
            size_hint_y=None,
            markup=True,
            height=5000,  # Adjust the height so it creates a scrollable area, theres a lot of text inside help
            halign='left',
            valign='top'
        )
        content.bind(size=content.setter('text_size'))
        scroll.add_widget(content)

        popup = Popup(
            title='Help',
            title_color=(1, 1, 1, 1),
            content=scroll,
            size_hint=(None, None),
            size=(1340, 1100),
            auto_dismiss=True
        )

        popup.open()

    def setup_ui(self):
        self.root_layout = FloatLayout()


        with self.root_layout.canvas.before:
            Color(*self.theme["background"])
            self.bg_rect = Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)

            self.border_color_box = Color(*self.theme["secondary"])  # Save the color object
            self.full_border = Line(width=14, rectangle=(0.1, 0.1, 0.1, 1))

        self.root_layout.bind(pos=self.update_full_border, size=self.update_full_border)

        def update_full_border(self, instance, value):
            self.full_border.rectangle = (instance.x, instance.y, instance.width, instance.height)

        self.root_layout.bind(pos=self.update_bg, size=self.update_bg)

        self.main_layout = BoxLayout(orientation='horizontal', spacing=10, padding=10, size_hint=(1, 1))
        self.root_layout.add_widget(self.main_layout)

        # Sidebar
        scroll = ScrollView(size_hint=(0.2, 1))
        self.sidebar = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        self.sidebar.bind(minimum_height=self.sidebar.setter('height'))
        scroll.add_widget(self.sidebar)
        self.sidebar_buttons = []
        self.main_layout.add_widget(scroll)

        self.sidebar_buttons = []
        self.selected_folder = None

        # Main content area
        content_frame = FloatLayout(size_hint=(0.6, 1))

        # Create centered box inside the content frame to wrap the label
        content_box = BoxLayout(size_hint=(1, 0.9), pos_hint={'center_x': 0.53, 'center_y': 0.5})

        self.reminder_area = FlickScrollView(
            size_hint=(1, 1),
            bar_width=20,
            scroll_type=['bars', 'content'],
            bar_color=(0.5, 0.5, 0.5, 0.8),
            bar_inactive_color=(0.3, 0.3, 0.3, 0.4),
            scroll_timeout=150
        )

        left_divider_x = Window.width * 0.19
        right_divider_x = Window.width * 0.72
        center_x_normalized = ((left_divider_x + right_divider_x) / 2) / Window.width

        self.viewing_label = Label(
            text='[b]Select a folder to view reminders[/b]',
            markup=True,
            font_size=50,
            size_hint=(None, None),
            size=(800, 100),
            pos_hint={'center_x': center_x_normalized, 'center_y': 0.5},
            halign='center',
            valign='middle'
        )
        self.viewing_label.bind(size=self.viewing_label.setter('text_size'))

        self.reminder_list = StackLayout(orientation='lr-tb', padding=10, spacing=10, size_hint_y=None)
        self.reminder_list.bind(minimum_height=self.reminder_list.setter('height'))

        self.reminder_area_layout = BoxLayout(orientation='vertical', size_hint_y=None)
        self.reminder_area_layout.bind(minimum_height=self.reminder_area_layout.setter('height'))

        self.reminder_area_layout.clear_widgets()

        self.reminder_area_layout.add_widget(self.viewing_label)
        self.reminder_area_layout.add_widget(self.reminder_list)
        self.reminder_area.add_widget(self.reminder_area_layout)

        # Add label to box, box to frame, frame to main layout
        content_box.add_widget(self.reminder_area)
        content_frame.add_widget(content_box)
        self.main_layout.add_widget(content_frame)


        button_wrapper = BoxLayout(
            padding=(10, 20),
            size_hint=(0.275, 0.5),
            pos_hint={'top': 1})
        button_layout = BoxLayout(orientation='vertical', spacing=25)

        # Buttons
        self.add_folder_btn = HoverButton(
            text='[b]Add Folder[/b]', markup=True,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )

        self.delete_folder_btn = HoverButton(
            text='[b]Delete Folder[/b]', markup=True,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )

        self.change_icon_btn = HoverButton(
            text='[b]Change Folder Icon[/b]', markup=True,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )

        self.add_reminder_btn = HoverButton(
            text='[b]Add Reminder[/b]', markup=True,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )
        self.add_reminder_btn.bind(on_press=self.add_reminder)

        self.change_theme_btn = HoverButton(text='[b]Change Theme[/b]', markup=True,
                                            background_normal='', background_color=self.theme["primary"]
                                            )
        self.change_theme_btn.bind(on_press=self.show_theme_popup)

        self.help_btn = HoverButton(
            text='[b]Help[/b]',
            markup=True,
            background_normal='',
            background_color=self.theme["primary"],
            app_ref=self
        )
        self.help_btn.bind(on_press=self.show_help_popup)

        # Bind actions
        self.add_folder_btn.bind(on_press=self.add_folder)
        self.delete_folder_btn.bind(on_press=self.delete_folder)
        self.change_icon_btn.bind(on_press=self.change_folder_icon)


        for btn in [self.add_folder_btn, self.delete_folder_btn, self.change_icon_btn, self.add_reminder_btn,
                    self.change_theme_btn, self.help_btn]:
            wrapper = BoxLayout(padding=(10, 5))
            wrapper.add_widget(btn)
            button_layout.add_widget(wrapper)

        # Add layout inside wrapper, then main app
        button_wrapper.add_widget(button_layout)
        self.main_layout.add_widget(button_wrapper)

        self.themed_buttons = [
            self.add_folder_btn,
            self.delete_folder_btn,
            self.change_icon_btn,
            self.add_reminder_btn,
            self.help_btn,
            self.change_theme_btn
        ]

        if not self.theme:
            self.theme = {
                "background": (0.2, 0.2, 0.2, 1),
                "primary": (0.3, 0.3, 0.7, 1),
                "secondary": (0.7, 0.3, 0.3, 1),
                "text": (1, 1, 1, 1)
            }

        with self.root_layout.canvas.before:
            self.bg_color = Color(*self.theme["background"])  # Store for later update
            self.bg_rect = Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)

            self.border_color_box = Color(*self.theme["secondary"])
            self.full_border = Line(width=14, rectangle=(0, 0, 0, 0))

        with self.main_layout.canvas.after:
            self.divider_color = Color(*self.theme["secondary"])
            self.divider_line_left = Line(width=8)
            self.divider_line_right = Line(width=8)

        with self.main_layout.canvas.after:
            self.border_color_line = Color(*self.theme["secondary"])
            self.divider_line_left = Line(width=8)
            self.divider_line_right = Line(width=8)  # Divider between middle and right columns

        def update_divider_lines(*args):
            # The left divider line sits at the right edge of the ScrollView (the left column)

            left_offset = 285
            right_offset = 1090

            left_divider_x = scroll.x + scroll.width + left_offset
            # Calculate the x-coordinate with the offset for the right divider line
            right_divider_x = content_frame.x + content_frame.width + right_offset
            y = self.main_layout.y
            height = self.main_layout.height
            self.divider_line_left.points = [left_divider_x, y, left_divider_x, y + height]
            self.divider_line_right.points = [right_divider_x, y, right_divider_x, y + height]

        self.main_layout.bind(pos=update_divider_lines, size=update_divider_lines)

        self.load_folders()

    def update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def show_theme_popup(self, instance):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)

        # --- Saved themes section ---
        scroll = ScrollView(size_hint=(1, 0.5))
        self.saved_themes_box = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=5,
            padding=(0, 5)
        )
        self.saved_themes_box.bind(minimum_height=self.saved_themes_box.setter('height'))

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM themes
            WHERE name IS NULL OR background IS NULL OR
                  "primary" IS NULL OR "secondary" IS NULL OR "text" IS NULL
        """)
        conn.commit()

        cursor.execute(
            'SELECT name, background, "primary", "secondary", "text" FROM themes WHERE name NOT IN ("Dark", "Light") ORDER BY id DESC')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            self.saved_themes_box.add_widget(Label(
                text="No Saved Themes",
                size_hint_y=None,
                height=40,
                halign='center'
            ))
        else:
            for row in rows:
                name, bg, primary, secondary, text = row
                theme_dict = {
                    "name": name,
                    "background": self.hex_to_rgba(bg),
                    "primary": self.hex_to_rgba(primary),
                    "secondary": self.hex_to_rgba(secondary),
                    "text": self.hex_to_rgba(text)
                }

                # Create a horizontal layout for each theme button and its delete button
                theme_row = BoxLayout(orientation='horizontal', spacing=7, size_hint_y=None, height=50)

                # Theme button
                theme_btn = HoverButton(
                    text=f"[b]{name}[/b]",
                    markup=True,
                    size_hint=(0.8, 1),
                    background_normal='',
                    background_color=self.theme["primary"],
                    app_ref=self
                )
                theme_btn.bind(on_press=lambda inst, t=theme_dict: self.load_custom_theme(t))

                delete_btn = HoverButton(
                    text='[b]X[/b]',
                    markup=True,
                    size_hint=(None, None),
                    size=(50, 40),
                    pos_hint={'center_y': 0.5},
                    background_normal='',
                    background_color=(1, 0, 0, 1),  # Bright red
                    color=(1, 1, 1, 1),  # White text
                    app_ref=self
                )

                delete_btn.bind(on_press=lambda inst, n=name: self.delete_theme(n))

                theme_row.add_widget(theme_btn)
                theme_row.add_widget(delete_btn)
                self.saved_themes_box.add_widget(theme_row)

        scroll.add_widget(self.saved_themes_box)
        layout.add_widget(scroll)

        # --- Mode Buttons (Dark / Light / Custom / Save) ---
        dark_btn = HoverButton(
            text="[b]Dark Mode[/b]", markup=True, size_hint_y=None, height=50,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )
        dark_btn.bind(on_press=self.set_dark_theme)

        light_btn = HoverButton(
            text="[b]Light Mode[/b]",
            markup=True,
            size_hint_y=None,
            height=50,
            app_ref=self
        )
        light_btn.bind(on_press=self.set_light_theme)

        custom_btn = HoverButton(
            text="[b]Custom Colors[/b]", markup=True, size_hint_y=None, height=50,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )
        custom_btn.bind(on_press=self.show_custom_theme_popup)

        save_btn = HoverButton(
            text="[b]Save Theme[/b]", markup=True, size_hint_y=None, height=50,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )
        save_btn.bind(on_press=self.prompt_save_theme)

        for btn in [dark_btn, light_btn, custom_btn, save_btn]:
            layout.add_widget(btn)

        self.theme_popup = Popup(
            title="Choose Theme",
            content=layout,
            size_hint=(None, None),
            size=(850, 750),
            auto_dismiss=True
        )
        self.theme_popup.open()

    def show_custom_theme_popup(self, instance=None):
        # Base layout for the popup (vertical layout: header + content)
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        header = BoxLayout(orientation='horizontal', size_hint=(1, None), height=40)
        header.add_widget(Label(size_hint_x=0.9))  # empty space for alignment

        close_btn = Button(
            text='X',
            size_hint_x=0.1,
            background_normal='',
            background_color=(1, 0.2, 0.2, 1),  # kinda red transparwnrt button
            color=(1, 1, 1, 1),  # white text
            bold=True
        )

        # Set up layout for the actual theme controls
        content_layout = BoxLayout(orientation='vertical', spacing=15, padding=10)


        for label_text in ["Primary", "Secondary", "Background", "Text"]:
            btn = HoverButton(
                text=f"[b]{label_text} Color[/b]",
                markup=True,
                size_hint=(1, None),
                height=100,
                background_normal='',
                background_color=self.theme["primary"],
                app_ref=self
            )
            # Bind to corresponding color type
            btn.bind(on_press=lambda inst, key=label_text.lower(): self.pick_color_for(key))
            content_layout.add_widget(btn)

        back_btn = HoverButton(
            text="[b]<-- Back[/b]",
            markup=True,
            size_hint=(1, None),
            height=50,
            background_normal='',
            background_color=(0.6, 0.6, 0.6, 1),
            app_ref=self
        )
        back_btn.bind(on_press=self.show_theme_popup)
        content_layout.add_widget(back_btn)

        # Combine header and content
        popup_layout.add_widget(header)
        popup_layout.add_widget(content_layout)

        # Create the popup and bind the close button
        self.theme_popup = Popup(
            title='Customize Theme Colors',
            content=popup_layout,
            size_hint=(None, None),
            size=(850, 750),
            auto_dismiss=False
        )
        close_btn.bind(on_press=self.theme_popup.dismiss)
        header.add_widget(close_btn)

        self.theme_popup.open()

    def pick_color_for(self, color_type):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        # Hex input row at the top
        hex_row = BoxLayout(size_hint=(1, None), height=70, spacing=10)
        hex_label = Label(text='Enter Hex:', size_hint=(0.2, 1), halign='right', valign='middle')
        hex_label.bind(size=hex_label.setter('text_size'))

        hex_input = TextInput(
            text='',
            size_hint=(0.8, 1),
            multiline=False,
            write_tab=False,
            halign='left',
            hint_text='#RRGGBB'
        )
        hex_row.add_widget(hex_label)
        hex_row.add_widget(hex_input)
        layout.add_widget(hex_row)

        # Color picker
        color_picker = ColorPicker(size_hint=(1, None), height=500)
        layout.add_widget(color_picker)

        # Color preview box
        preview_canvas = BoxLayout(size_hint=(1, None), height=40, padding=5)
        layout.add_widget(preview_canvas)

        # Convert hex input → color
        def hex_to_color(hex_str):
            hex_str = hex_str.strip().lstrip('#')
            if len(hex_str) != 6:
                return None
            try:
                r = int(hex_str[0:2], 16) / 255.0
                g = int(hex_str[2:4], 16) / 255.0
                b = int(hex_str[4:6], 16) / 255.0
                return [r, g, b, 1.0]
            except ValueError:
                return None

        # Sync when typing in hex
        def on_hex_input(instance, value):
            color = hex_to_color(value)
            if color:
                color_picker.color = color

        hex_input.bind(text=on_hex_input)

        # Update hex + preview from picker
        def update_color_widgets(instance, *args):
            color = color_picker.color
            r, g, b, a = color
            hex_input.text = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"

            preview_canvas.canvas.before.clear()
            with preview_canvas.canvas.before:
                Color(r, g, b, 1)
                Rectangle(pos=preview_canvas.pos, size=preview_canvas.size)

        color_picker.bind(color=update_color_widgets)
        preview_canvas.bind(pos=update_color_widgets, size=update_color_widgets)
        update_color_widgets(color_picker, color_picker.color)

        # Apply / Cancel buttons
        button_row = BoxLayout(size_hint=(1, None), height=50, spacing=10)

        apply_btn = HoverButton(
            text='[b]Apply[/b]',
            markup=True,
            background_color=self.theme["primary"],
            background_normal='',
            app_ref=self
        )
        cancel_btn = HoverButton(
            text='[b]Cancel[/b]',
            markup=True,
            background_color=self.theme["secondary"],
            background_normal='',
            app_ref=self
        )
        button_row.add_widget(apply_btn)
        button_row.add_widget(cancel_btn)
        layout.add_widget(button_row)

        # Remove any leftover empty layouts that might be adding space
        for child in list(layout.children):
            if isinstance(child, BoxLayout) and len(child.children) == 0 and child.height > 0:
                layout.remove_widget(child)

        popup = Popup(
            title=f"Choose {color_type.capitalize()} Color",
            content=layout,
            size_hint=(None, None),
            size=(1000, 900),
            auto_dismiss=False
        )

        def apply_color(_):
            self.theme[color_type.lower()] = tuple(color_picker.color)
            self.apply_theme()
            popup.dismiss()

        apply_btn.bind(on_press=apply_color)
        cancel_btn.bind(on_press=popup.dismiss)

        popup.open()

    def clean_color_picker_ui(self, color_picker):
        target_box = None  # this is where sliders like R, G, B, A live

        for child in color_picker.children:
            if isinstance(child, BoxLayout):
                for subchild in child.children:
                    if isinstance(subchild, Slider):
                        if not target_box:
                            target_box = child

                to_remove = []
                for w in child.children:
                    if hasattr(w, 'label'):
                        label = w.label.text.strip().lower()
                        if label in ['x', 'a:', 'alpha', 'v:', 'value']:
                            to_remove.append(w)

                for w in to_remove:
                    child.remove_widget(w)

        return target_box  # custom ui insert

    def prompt_save_theme(self, instance=None):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        label = Label(text="Enter a name for your theme:")
        theme_name_input = TextInput(multiline=False, hint_text="e.g. Ocean Breeze")

        save_button = HoverButton(
            text='[b]Save[/b]', markup=True,
            background_normal='',
            background_color=self.theme["primary"],
            app_ref=self
        )

        cancel_button = HoverButton(
            text='[b]Cancel[/b]', markup=True,
            background_normal='',
            background_color=self.theme["secondary"],
            app_ref=self
        )

        button_row = BoxLayout(size_hint=(1, None), height=40, spacing=10)
        button_row.add_widget(save_button)
        button_row.add_widget(cancel_button)

        layout.add_widget(label)
        layout.add_widget(theme_name_input)
        layout.add_widget(button_row)

        popup = Popup(
            title="Save Theme",
            content=layout,
            size_hint=(None, None),
            size=(500, 300),
            auto_dismiss=True
        )

        def on_save(_):
            name = theme_name_input.text.strip()
            if name:
                self.save_theme_to_db(name)
                popup.dismiss()

        save_button.bind(on_press=on_save)
        cancel_button.bind(on_press=popup.dismiss)

        popup.open()

    def toggle_theme(self, instance):
        if self.theme["background"] == (0.204, 0.208, 0.212, 1):  # currently dark
            self.theme = {
                "background": (1, 1, 0.9, 1),
                "primary": (0, 0, 1, 1),
                "secondary": (1, 0, 0, 1)
            }
        else:
            self.theme = {
                "background": (0.204, 0.208, 0.212, 1),
                "primary": (0.239, 0.059, 0.349, 1),
                "secondary": (0.086, 0.616, 0.651, 1)
            }

        self.apply_theme()
        self.save_theme_to_db()

    def apply_theme(self):
        self.bg_color.rgba = self.theme["background"]
        self.border_color.rgba = self.theme["secondary"]
        self.divider_color.rgba = self.theme["secondary"]

        # Update buttons if defined
        for btn in getattr(self, 'themed_buttons', []):
            btn.default_color = self.theme["primary"]
            btn.hover_color = self.theme["secondary"]
            btn.background_color = btn.default_color
            btn.color = self.theme["text"]  # this line sets the button text color

        # Update border and divider colors
        if hasattr(self, "border_color_box"):
            self.border_color_box.rgba = self.theme["secondary"]

        if hasattr(self, "divider_color"):
            self.divider_color.rgba = self.theme["secondary"]

        if hasattr(self, "border_color_line"):
            self.border_color_line.rgba = self.theme["secondary"]

        # Update viewing label (center message when no folder is selected)
        if hasattr(self, "viewing_label"):
            self.viewing_label.color = self.theme["text"]


        # Update reminder row button colors
        if hasattr(self, "reminder_list"):
            for child in self.reminder_list.children:
                if isinstance(child, DraggableReminder):
                    child.text_btn.background_color = self.theme["primary"]
                    child.text_btn.color = self.theme["text"]
                    if hasattr(child.complete_btn, "update_graphics"):
                        child.complete_btn.update_graphics()

        for folder_btn in getattr(self, "sidebar_buttons", []):
            folder_btn.default_color = self.theme["primary"]
            folder_btn.hover_color = self.theme["secondary"]
            folder_btn.background_color = folder_btn.default_color
            folder_btn.color = self.theme["text"]  # sets sidebar text color

        self.root_layout.canvas.ask_update()
        self.main_layout.canvas.ask_update()
        self.load_folders()

        # Reapply theme to current folder's reminders
        if hasattr(self, "selected_folder") and self.selected_folder:
            folder_name = self.selected_folder.replace('[b]', '').replace('[/b]', '')
            self.load_reminders(folder_name)

    def load_last_theme(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT background, "primary", "secondary", "text" FROM themes WHERE selected_theme = 1 ORDER BY id DESC LIMIT 1'
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            self.theme = {
                "background": self.hex_to_rgba(row[0]),
                "primary": self.hex_to_rgba(row[1]),
                "secondary": self.hex_to_rgba(row[2]),
                "text": self.hex_to_rgba(row[3])
            }
        else:
            # Keep default fallback theme without overwriting user choice
            if not hasattr(self, "theme"):
                self.theme = {
                    "background": (0.2, 0.2, 0.2, 1),
                    "primary": (0.3, 0.3, 0.7, 1),
                    "secondary": (0.7, 0.3, 0.3, 1),
                    "text": (1, 1, 1, 1)
                }

    def hex_to_rgba(self, hex_color):
        hex_color = hex_color.lstrip('#')
        lv = len(hex_color)
        return tuple(int(hex_color[i:i + lv // 3], 16) / 255.0 for i in range(0, lv, lv // 3)) + (1,)

    def rgba_to_hex(self, rgba):
        return "#{:02x}{:02x}{:02x}".format(
            int(rgba[0] * 255),
            int(rgba[1] * 255),
            int(rgba[2] * 255)
        )

    def save_theme_to_db(self, name=None):
        if not name:
            self.prompt_save_theme()
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Unselect all other themes first
        cursor.execute("UPDATE themes SET selected_theme = 0")

        # Save new theme and mark it as selected
        cursor.execute("""
            INSERT INTO themes (name, background, "primary", "secondary", "text", selected_theme)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (
            name,
            self.rgba_to_hex(self.theme["background"]),
            self.rgba_to_hex(self.theme["primary"]),
            self.rgba_to_hex(self.theme["secondary"]),
            self.rgba_to_hex(self.theme["text"])
        ))

        conn.commit()
        conn.close()

        # Only call this if the theme popup is already built
        if hasattr(self, "saved_themes_box"):
            self.refresh_saved_themes()

    def clear_completed_reminders(self, instance):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE folder_name = 'Completed'")
        conn.commit()
        conn.close()

        # Refresh only if currently viewing Completed
        if self.selected_folder and 'Completed' in self.selected_folder:
            self.load_reminders("Completed")

    def refresh_saved_themes(self):
        self.saved_themes_box.clear_widgets()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT name, background, "primary", "secondary", "text" FROM themes WHERE name NOT IN ("Dark", "Light") ORDER BY id DESC')
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            self.saved_themes_box.add_widget(Label(
                text="No Saved Themes",
                size_hint_y=None,
                height=40,
                halign='center'
            ))
        else:
            for row in rows:
                name, bg, primary, secondary, text = row

                # Skip any theme that has None values (incomplete)
                if None in (name, bg, primary, secondary, text):
                    continue

                theme_dict = {
                    "name": name,
                    "background": self.hex_to_rgba(bg),
                    "primary": self.hex_to_rgba(primary),
                    "secondary": self.hex_to_rgba(secondary),
                    "text": self.hex_to_rgba(text)
                }

                btn = HoverButton(
                    text=f"[b]{name}[/b]",
                    markup=True,
                    size_hint_y=None,
                    height=40,
                    background_normal='',
                    background_color=self.theme["primary"],
                    app_ref=self
                )
                btn.bind(on_press=lambda inst, t=theme_dict: self.load_custom_theme(t))
                self.saved_themes_box.add_widget(btn)

    def load_folders(self):
        self.sidebar.clear_widgets()
        self.sidebar_buttons.clear()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name, folder_order, image_path FROM folders")
        folders = cursor.fetchall()

        # Custom sort: Pinned, Non-Completed, Completed always on top
        priority = {'Pinned': 0, 'Recurring': 1, 'Non-Completed': 2, 'Completed': 3}
        folders.sort(key=lambda x: (priority.get(x[0], 3), x[1]))
        conn.close()

        for folder in folders:
            name, order, image_path = folder

            if name == "Completed":
                icon_path = "Images for App/check.png"
            elif name == "Recurring":
                icon_path = "Images for App/recurring.png"
            elif name == "Non-Completed":
                icon_path = "Images for App/incomplete.png"
            elif name == "Pinned":
                icon_path = "Images for App/pinned.png"
            elif image_path:
                icon_path = image_path
            else:
                icon_path = "Images for App/anything.png"

            if name in ["Pinned", "Completed", "Non-Completed"]:
                folder_widget = FolderButton(name, icon_path=icon_path, app_ref=self)
            else:
                folder_widget = DraggableFolder(name, icon_path=icon_path, app_ref=self)

            folder_widget.label.bind(on_press=self.switch_view)
            self.sidebar_buttons.append(folder_widget.label)
            self.sidebar.add_widget(folder_widget)

        # Add sidebar buttons to themed buttons so they respond to theme toggle
        self.themed_buttons.extend(self.sidebar_buttons)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name, folder_order FROM folders ORDER BY folder_order")
        rows = cursor.fetchall()
        conn.close()

    def add_folder(self, instance):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        text_input = TextInput(hint_text="Enter folder name", multiline=False, size_hint=(1, 0.5))
        add_button = Button(text="Add", size_hint=(1, 0.5),
                            background_color=self.theme["primary"])  # matches purple theme

        layout.add_widget(text_input)
        layout.add_widget(add_button)

        popup = Popup(title="New Folder", content=layout, size_hint=(None, None), size=(600, 400))
        popup.open()
        Clock.schedule_once(lambda dt: setattr(text_input, 'focus', True), 0.1)

        def on_add_button_pressed(_):
            folder_name = text_input.text.strip()
            if folder_name:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO folders (name) VALUES (?)", (folder_name,))
                conn.commit()
                conn.close()
                popup.dismiss()
                self.load_folders()

        add_button.bind(on_press=on_add_button_pressed)
        text_input.bind(on_text_validate=on_add_button_pressed)

    def delete_folder(self, instance):
        folder_name = self.selected_folder

        if not folder_name:
            popup = Popup(title="No Folder Selected",
                          content=Label(text="Please select a folder"),
                          size_hint=(None, None), size=(400, 200))
            popup.open()
            return

        folder_name_clean = folder_name.replace('[b]', '').replace('[/b]', '')

        if folder_name_clean in ["Completed", "Non-Completed", "Pinned"]:
            message = Label(
                text=f"[b]{folder_name_clean} cannot be deleted[/b]\nPermanent folder",
                markup=True,
                halign='center',
                valign='middle'
            )
            message.bind(size=message.setter('text_size'))  # enables centering

            popup = Popup(
                title="Delete Folder",
                content=message,
                size_hint=(None, None),
                size=(400, 200)
            )
            popup.open()
            return

        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        message = Label(
            text=f"[b]Are you sure you want to delete '{folder_name_clean}'?[/b]",
            markup=True,
            halign='center',
            valign='middle'
        )
        message.bind(size=message.setter('text_size'))  # Enables wrapping
        layout.add_widget(message)

        confirm_btn = Button(
            text="Delete",
            background_normal='',
            background_color=(0.8, 0.2, 0.2, 1))

        cancel_btn = Button(
            text="Cancel",
            background_normal='',
            background_color=self.theme["primary"])

        btn_box = BoxLayout(spacing=10)
        btn_box.add_widget(confirm_btn)
        btn_box.add_widget(cancel_btn)
        layout.add_widget(btn_box)

        popup = Popup(title="Confirm Deletion", content=layout, size_hint=(None, None), size=(600, 300))
        popup.open()

        def on_confirm_delete(_):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM folders WHERE name = ?", (folder_name_clean,))
            conn.commit()
            conn.close()
            popup.dismiss()
            self.load_folders()
            self.selected_folder = None

        confirm_btn.bind(on_press=on_confirm_delete)
        cancel_btn.bind(on_press=popup.dismiss)

    def show_first_theme_popup(self):
        layout = BoxLayout(orientation='vertical', spacing=20, padding=20)

        label = Label(
            text="[b]Choose your preferred theme:[/b]",
            markup=True,
            font_size=36,
            halign='center',
            valign='middle',
            size_hint=(1, None),
            height=60
        )
        label.bind(size=label.setter('text_size'))

        btn_row = BoxLayout(spacing=10, size_hint=(1, None), height=60)

        dark_btn = HoverButton(
            text='[b]Dark Mode[/b]',
            markup=True,
            background_normal='',
            background_color=(0.2, 0.2, 0.2, 1),
            color=(1, 1, 1, 1),
            app_ref=self
        )

        light_btn = HoverButton(
            text='[b]Light Mode[/b]',
            markup=True,
            background_normal='',
            background_color=(1, 1, 1, 1),
            color=(0, 0, 0, 1),
            app_ref=self
        )

        btn_row.add_widget(dark_btn)
        btn_row.add_widget(light_btn)

        layout.add_widget(label)
        layout.add_widget(btn_row)

        popup = Popup(
            title='Welcome!',
            content=layout,
            size_hint=(None, None),
            size=(700, 350),
            auto_dismiss=False,
            background='',
            background_color=self.theme["background"]
        )

        def choose_theme(theme_name):
            if theme_name == 'dark':
                self.set_dark_theme()
            elif theme_name == 'light':
                self.set_light_theme()

            # Save selected built-in theme to DB as active
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Unselect all previously selected themes
            cursor.execute("UPDATE themes SET selected_theme = 0")

            # Insert or replace the chosen built-in theme
            cursor.execute("""
                INSERT OR REPLACE INTO themes (name, background, "primary", "secondary", "text", selected_theme)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                theme_name.capitalize(),  # "Dark" or "Light"
                self.rgba_to_hex(self.theme["background"]),
                self.rgba_to_hex(self.theme["primary"]),
                self.rgba_to_hex(self.theme["secondary"]),
                self.rgba_to_hex(self.theme["text"])
            ))

            conn.commit()
            conn.close()

            popup.dismiss()

        dark_btn.bind(on_press=lambda x: choose_theme('dark'))
        light_btn.bind(on_press=lambda x: choose_theme('light'))

        popup.open()

    def change_folder_icon(self, instance):
        if not self.selected_folder:
            popup = Popup(title="No Folder Selected",
                          content=Label(text="Please select a folder to change the icon"),
                          size_hint=(None, None), size=(670, 200))
            popup.open()
            return

        folder_name = self.selected_folder.replace('[b]', '').replace('[/b]', '')

        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        instruction = Label(
            text='[b]Drop an image here[/b]',
            markup=True,
            size_hint=(1, None),
            height=40,
            halign='center',
            valign='middle'
        )
        instruction.bind(size=instruction.setter('text_size'))

        preview_image = Image(
            source='',
            size_hint=(1, 1),
            allow_stretch=True,
            keep_ratio=True
        )

        layout.add_widget(instruction)
        layout.add_widget(preview_image)

        # Add confirm + cancel button row (hidden initially)
        button_row = BoxLayout(size_hint=(1, None), height=50, spacing=10)
        confirm_btn = Button(text='Confirm', background_color=self.theme["primary"])
        cancel_btn = Button(text='Cancel', background_color=self.theme["secondary"])
        button_row.add_widget(confirm_btn)
        button_row.add_widget(cancel_btn)
        button_row.opacity = 0  # Hidden until a file is dropped
        layout.add_widget(button_row)

        popup = Popup(
            title=f"Change Icon for: {folder_name}",
            content=layout,
            size_hint=(None, None),
            size=(600, 500),
            auto_dismiss=True
        )
        popup.open()

        def on_file_drop(window, file_path_bytes):
            file_path = file_path_bytes.decode('utf-8')
            if file_path.lower().endswith('.png'):
                preview_image.source = file_path
                preview_image.reload()
                button_row.opacity = 1  # Show buttons
                confirm_btn.file_path = file_path  # Store path
            else:
                Popup(
                    title="Invalid File",
                    content=Label(text="Please add a .png image"),
                    size_hint=(None, None),
                    size=(400, 200)
                ).open()

        def on_confirm(_):
            file_path = getattr(confirm_btn, 'file_path', None)
            if file_path:
                self.update_folder_icon(file_path, folder_name)
            popup.dismiss()

        def on_cancel(_):
            popup.dismiss()

        confirm_btn.bind(on_press=on_confirm)
        cancel_btn.bind(on_press=on_cancel)

        Window.bind(on_dropfile=on_file_drop)
        popup.bind(on_dismiss=lambda *_: Window.unbind(on_dropfile=on_file_drop))

    def update_folder_icon(self, file_path, folder_name):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE folders SET image_path = ? WHERE name = ?", (file_path, folder_name))
        conn.commit()
        conn.close()
        self.load_folders()

    def load_reminders(self, folder_name):
        self.reminder_list.clear_widgets()
        self.reminder_area_layout.clear_widgets()

        folder_name_clean = folder_name.replace('[b]', '').replace('[/b]', '')

        if folder_name_clean == "Completed":
            clear_completed_btn = HoverButton(
                text='[b]Clear All[/b]',
                markup=True,
                size_hint=(None, None),
                size=(200, 40),
                background_normal='',
                background_color=self.theme["primary"],
                app_ref=self
            )
            clear_completed_btn.bind(on_press=self.clear_completed_reminders)
            self.reminder_area_layout.add_widget(clear_completed_btn)

        # Fetch reminders and all notify_at values
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Main reminders
        cursor.execute("""
            SELECT text, urgency_level
            FROM reminders
            WHERE folder_name = ?
            ORDER BY reminder_order ASC
        """, (folder_name_clean,))
        reminders = cursor.fetchall()

        # All notify_at timestamps
        cursor.execute("""
            SELECT reminder_text, notify_at
            FROM reminder_notifications
            WHERE folder_name = ?
        """, (folder_name_clean,))
        notify_map = {}
        for text, notify_at in cursor.fetchall():
            notify_map.setdefault(text, []).append(notify_at)

        # Also include the notify_at from reminders table itself
        cursor.execute("""
            SELECT text, notify_at FROM reminders
            WHERE folder_name = ?
        """, (folder_name_clean,))
        for text, notify_at in cursor.fetchall():
            if notify_at:  # ignore NULLs
                notify_map.setdefault(text, []).append(notify_at)


        conn.close()

        # Show "No reminders" message if empty
        if not reminders:
            self.viewing_label.text = f"[b]No reminders in '{folder_name_clean}'[/b]"
            self.reminder_area_layout.add_widget(self.viewing_label)
            return

        for text, urgency in reminders:
            raw_dates = notify_map.get(text, [])

            # Normalize to list
            if isinstance(raw_dates, str):
                dates = [raw_dates]
            elif isinstance(raw_dates, list):
                dates = raw_dates
            elif raw_dates is None:
                dates = []
            else:
                print(f"[WARN] Unrecognized notify_at format: {raw_dates} for {text}")
                dates = []

            show_urgency = folder_name_clean != "Completed"

            btn = DraggableReminder(
                reminder_text=text,
                urgency_level=urgency if show_urgency else None,
                folder_name=folder_name_clean,
                notify_at=dates,
                app_ref=self
            )
            self.reminder_list.add_widget(btn)

        now = datetime.now()
        for text, notify_list in notify_map.items():
            for notify_str in notify_list:
                try:
                    dt = datetime.fromisoformat(notify_str)
                    delay = (dt - now).total_seconds()
                except Exception as e:
                    print(f"[ERROR] Could not parse notify_at '{notify_str}' for reminder '{text}': {e}") # Debug message

        self.reminder_area_layout.add_widget(self.reminder_list)

        def split_reminder_instances(reminder_text: str, notify_at_list: List[str]) -> List[
            Tuple[str, Union[str, List[str]]]]:
            """
            Given a reminder text and list of ISO datetime strings, split them into individual reminders for past events
            and a grouped reminder for future events.

            Returns:
                List of tuples with (reminder_text, notify_at) where notify_at can be a string or list of strings.
            """
            now = datetime.now()
            past_reminders = []
            future_notify_at = []

            for notify_at_str in notify_at_list:
                try:
                    dt = datetime.fromisoformat(notify_at_str)
                    if dt < now:
                        formatted_date = dt.strftime("%b %d, %Y")
                        labeled_text = f"{reminder_text} ({formatted_date})"
                        past_reminders.append((labeled_text, notify_at_str))
                    else:
                        future_notify_at.append(notify_at_str)
                except ValueError:
                    continue  # Skip malformed dates

            result = past_reminders
            if future_notify_at:
                result.append((reminder_text, future_notify_at))

            return result

    def add_reminder(self, instance):
        if not self.selected_folder:
            popup = Popup(title="No Folder Selected",
                          content=Label(text="Please select a folder first."),
                          size_hint=(None, None), size=(600, 400))
            popup.open()
            return

        folder_clean = self.selected_folder.replace('[b]', '').replace('[/b]', '')

        if folder_clean == "Completed":
            popup = Popup(title="Invalid Folder",
                          content=Label(text="Cannot Add To Completed folder."),
                          size_hint=(None, None), size=(700, 400))
            popup.open()
            return

        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        spinner_height = 80
        now = datetime.now()
        month_names = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]

        text_input = TextInput(
            hint_text="Reminder text",
            multiline=False,
            size_hint=(1, None),
            height=105
        )

        urgency_spinner = Spinner(
            text='No Urgency',
            values=('No Urgency', 'Medium', 'High'),
            size_hint_y=None,
            height=spinner_height
        )

        recurring_spinner = Spinner(
            text='Make Recurring?',
            values=('Yes', 'No'),
            size_hint_y=None,
            height=spinner_height
        )

        # Date inputs
        date_label = Label(text="[b]Date (Y/M/D)[/b]", markup=True, size_hint_y=None, height=20)

        year_spinner = Spinner(
            text=str(now.year),
            values=[str(y) for y in range(now.year, now.year + 5)],
            size_hint_y=None,
            height=spinner_height
        )
        month_spinner = Spinner(
            text=f"{now.month} - {month_names[now.month - 1]}",
            values=[f"{i + 1} - {month_names[i]}" for i in range(12)],
            size_hint_y=None,
            height=spinner_height
        )
        day_spinner = Spinner(
            text=str(now.day),
            values=[str(d) for d in range(1, 32)],
            size_hint_y=None,
            height=spinner_height
        )

        date_box = BoxLayout(size_hint=(1, None), height=spinner_height, spacing=5)
        date_box.add_widget(year_spinner)
        date_box.add_widget(month_spinner)
        date_box.add_widget(day_spinner)


        # Time inputs
        time_label = Label(text="[b]Time (12h format)[/b]", markup=True, size_hint_y=None, height=40)

        hour_spinner = Spinner(
            text="12",
            values=[str(h) for h in range(1, 13)],
            size_hint_y=None,
            height=spinner_height
        )

        ampm_spinner = Spinner(
            text="PM",
            values=["AM", "PM"],
            size_hint_y=None,
            height=spinner_height
        )

        minute_spinner = Spinner(
            text="00",
            values=[f"{m:02}" for m in range(0, 60)],
            size_hint_y=None,
            height=spinner_height
        )

        time_box = BoxLayout(size_hint=(1, None), height=spinner_height, spacing=5)
        time_box.add_widget(hour_spinner)
        time_box.add_widget(minute_spinner)
        time_box.add_widget(ampm_spinner)

        add_button = HoverButton(
            text='[b]Add Reminder[/b]',
            markup=True,
            size_hint_y=None,
            height=50,
            background_normal='',
            background_color=self.theme["primary"],
            app_ref=self
        )

        # Add widgets to layout
        layout.add_widget(text_input)
        layout.add_widget(urgency_spinner)
        layout.add_widget(recurring_spinner)

        spacer = Widget(size_hint_y=None, height=15)
        layout.add_widget(spacer)

        layout.add_widget(date_label)
        layout.add_widget(date_box)

        spacer = Widget(size_hint_y=None, height=15)
        layout.add_widget(spacer)

        layout.add_widget(time_label)
        layout.add_widget(time_box)
        layout.add_widget(add_button)

        popup = Popup(title="New Reminder", content=layout, size_hint=(None, None), size=(1100, 800))
        popup.open()
        Clock.schedule_once(lambda dt: setattr(text_input, 'focus', True), 0.1)

        def on_add(_):
            reminder_text = text_input.text.strip()

            add_to_recurring = recurring_spinner.text == "Yes"

            urgency_map = {'No Urgency': 1, 'Medium': 2, 'High': 3}
            urgency_level = urgency_map.get(urgency_spinner.text, 1)

            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            if reminder_text:
                year = int(year_spinner.text)
                month = int(month_spinner.text.split(" - ")[0])
                day = int(day_spinner.text)

                hour = int(hour_spinner.text)
                minute = int(minute_spinner.text)
                ampm = ampm_spinner.text

                # Convert 12h → 24h
                if ampm == "PM" and hour != 12:
                    hour += 12
                elif ampm == "AM" and hour == 12:
                    hour = 0

                notify_at = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"

                _, max_day = monthrange(year, month)
                if day > max_day:
                    Popup(
                        title="Invalid Date",
                        content=Label(text=f"{month_names[month - 1]} {year} has only {max_day} days."),
                        size_hint=(None, None), size=(450, 200)
                    ).open()
                    return

                cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = ?", (folder_clean,))
                max_order = cursor.fetchone()[0]
                next_order = (max_order + 1) if max_order is not None else 0

                # Always insert into the original folder
                cursor.execute("""
                    INSERT INTO reminders (text, folder_name, reminder_order, urgency_level, notify_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (reminder_text, folder_clean, next_order, urgency_level, notify_at))

                # Also insert into Recurring if selected
                if add_to_recurring:
                    cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = 'Recurring'")
                    max_rec_order = cursor.fetchone()[0]
                    next_rec_order = (max_rec_order + 1) if max_rec_order is not None else 0

                    cursor.execute("""
                        INSERT INTO reminders (text, folder_name, reminder_order, urgency_level, notify_at)
                        VALUES (?, 'Recurring', ?, ?, ?)
                    """, (reminder_text, next_rec_order, urgency_level, notify_at))

                if urgency_level == 3 and folder_clean != "Pinned":
                    cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = 'Pinned'")
                    max_pinned_order = cursor.fetchone()[0]
                    next_pinned_order = (max_pinned_order + 1) if max_pinned_order is not None else 0

                    cursor.execute("""
                        INSERT INTO reminders (text, folder_name, reminder_order, urgency_level)
                        VALUES (?, 'Pinned', ?, ?)
                    """, (reminder_text, next_pinned_order, urgency_level))

                if folder_clean != "Non-Completed" and not add_to_recurring:
                    cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = 'Non-Completed'")
                    max_nc_order = cursor.fetchone()[0]
                    next_nc_order = (max_nc_order + 1) if max_nc_order is not None else 0

                    cursor.execute("""
                        INSERT INTO reminders (text, folder_name, reminder_order, urgency_level, notify_at)
                        VALUES (?, 'Non-Completed', ?, ?, ?)
                    """, (reminder_text, next_nc_order, urgency_level, notify_at))

                conn.commit()
                conn.close()

                # Schedule notification
                notify_dt = datetime.strptime(notify_at, "%Y-%m-%d %H:%M")
                now = datetime.now()
                delay = (notify_dt - now).total_seconds()

                if delay > 0:
                    formatted_time = notify_dt.strftime("%I:%M %p on %b %d, %Y")
                    notification_body = f"{reminder_text}\nScheduled for {formatted_time}"

                    Clock.schedule_once(
                        lambda dt: send_mac_notification("Reminder", notification_body),
                        delay
                    )

                popup.dismiss()
                self.load_reminders(folder_clean)

        add_button.bind(on_press=on_add)
        text_input.bind(on_text_validate=on_add)

    def set_dark_theme(self, instance=None):
        self.theme = {
            "background": (0.204, 0.208, 0.212, 1),
            "primary": (0.239, 0.059, 0.349, 1),
            "secondary": (0.086, 0.616, 0.651, 1),
            "text": (1, 1, 1, 1)  # white text
        }
        self.save_theme_to_db(name="Dark")
        self.apply_theme()

    def set_light_theme(self, instance=None):
        self.theme = {
            "background": (0.91, 0.902, 0.875, 1),  # off-white
            "primary": (0.255, 0.588, 0.384, 1),  # spring green
            "secondary": (0.176, 0.176, 0.231, 1),  # arctic black/blue
            "text": (0, 0, 0, 1)  # black text
        }
        self.save_theme_to_db(name="Light")
        self.apply_theme()

    def prompt_save_theme_to_db(self, instance=None):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Ask user for a name
        def save_with_name(name):
            cursor.execute("""
                INSERT INTO themes (name, background, "primary", "secondary", "text")
                VALUES (?, ?, ?, ?, ?)
            """, (
                name,
                self.rgba_to_hex(self.theme["background"]),
                self.rgba_to_hex(self.theme["primary"]),
                self.rgba_to_hex(self.theme["secondary"]),
                self.rgba_to_hex(self.theme["text"])
            ))
            conn.commit()
            conn.close()

            if hasattr(self, "theme_popup"):
                self.theme_popup.dismiss()
            self.show_theme_popup(None)  # Refresh the list

        # Prompt user for theme name
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        input_box = TextInput(hint_text="Theme name", multiline=False)
        save_btn = Button(text="Save")

        layout.add_widget(input_box)
        layout.add_widget(save_btn)

        popup = Popup(
            title="Confirm Name",
            content=layout,
            size_hint=(None, None),
            size=(550, 375),
            auto_dismiss=True
        )

        save_btn.bind(on_press=lambda inst: (
            save_with_name(input_box.text.strip()) if input_box.text.strip() else None,
            popup.dismiss()
        ))
        popup.open()

    def load_custom_theme(self, theme_dict):
        self.theme = {
            "background": theme_dict["background"],
            "primary": theme_dict["primary"],
            "secondary": theme_dict["secondary"],
            "text": theme_dict.get("text", (1, 1, 1, 1))
        }

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE themes SET selected_theme = 0")
        cursor.execute("UPDATE themes SET selected_theme = 1 WHERE name = ?", (theme_dict["name"],))
        conn.commit()
        conn.close()

        self.apply_theme()

    def delete_theme(self, theme_name):
        if theme_name in ['Dark', 'Light']: # Set perma theme properties
            layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
            message = Label(
                text=f"'{theme_name}' is a permanent built-in theme and cannot be deleted.",
                halign='center',
                valign='middle'
            )
            layout.add_widget(message)
            popup = Popup(
                title="Protected Theme",
                content=layout,
                size_hint=(None, None),
                size=(400, 200)
            )
            popup.open()
            return

        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        message = Label(
            text=f"[b]Are you sure you want to delete '{theme_name}'?[/b]",
            markup=True,
            halign='center',
            valign='middle'
        )
        message.bind(size=message.setter('text_size'))

        confirm_btn = HoverButton(
            text='[b]Delete[/b]',
            markup=True,
            background_normal='',
            background_color=(0.8, 0.2, 0.2, 1),
            app_ref=self
        )
        cancel_btn = HoverButton(
            text='[b]Cancel[/b]',
            markup=True,
            background_normal='',
            background_color=self.theme["primary"],
            app_ref=self
        )

        button_row = BoxLayout(spacing=10)
        button_row.add_widget(confirm_btn)
        button_row.add_widget(cancel_btn)

        layout.add_widget(message)
        layout.add_widget(button_row)

        popup = Popup(
            title="Confirm Deletion",
            content=layout,
            size_hint=(None, None),
            size=(500, 300)
        )

        def on_confirm(_):
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM themes WHERE name = ?", (theme_name,))
            conn.commit()
            conn.close()
            popup.dismiss()
            self.show_theme_popup(None)  # Refresh list

        confirm_btn.bind(on_press=on_confirm)
        cancel_btn.bind(on_press=popup.dismiss)
        popup.open()

    def switch_view(self, instance):
        folder_name = instance.text

        self.selected_folder = folder_name
        folder_clean = folder_name.replace('[b]', '').replace('[/b]', '')

        # Load reminders for this folder
        self.load_reminders(folder_clean)

    def create_complete_button(self, reminder_text, folder_name):
        btn = Button(
            size_hint=(None, None),
            size=(25, 25),
            background_normal='',
            background_color=(0, 0, 0, 0)  # Make button background transparent
        )
        btn.bind(on_press=lambda instance: self.mark_as_completed(reminder_text, folder_name))

        with btn.canvas.before:
            Color(*self.theme["secondary"])  # Use app's theme secondary color
            btn.circle = Ellipse(pos=btn.pos, size=btn.size)

        def update_circle(instance, value):
            btn.circle.pos = btn.pos
            btn.circle.size = btn.size

        btn.bind(pos=update_circle, size=update_circle)

        return btn


# Runs the script
if __name__ == "__main__":
    RemindersApp().run()
