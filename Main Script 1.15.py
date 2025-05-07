import sqlite3
import os
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, Rectangle
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.core.window import Window
from kivy.graphics import Line
from kivy.clock import Clock
from kivy.uix.image import Image
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.stacklayout import StackLayout
from kivy.graphics import Ellipse
from kivy.uix.behaviors import DragBehavior
from kivy.animation import Animation
from kivy.uix.scrollview import ScrollView
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.properties import NumericProperty
import time
from kivy.uix.spinner import Spinner
from kivy.config import Config
import subprocess
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')


DB_PATH = os.path.join(os.path.dirname(__file__), "reminders.db")

def send_mac_notification(title, message):
    script = f'display notification "{message}" with title "{title}"'
    subprocess.run(["osascript", "-e", script])

os.system('osascript -e \'display notification "This is a test notification!" with title "Reminder App"\'')

# Database Setup
def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        image_path TEXT DEFAULT '',
        folder_order INTEGER DEFAULT 0
    )
    ''')

    # Create reminders table with all required columns from the start
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
    CREATE TABLE IF NOT EXISTS themes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        background TEXT,
        "primary" TEXT,
        "secondary" TEXT,
        "text" TEXT
    )
    ''')

    cursor.execute("INSERT OR IGNORE INTO folders (name) VALUES ('Pinned'), ('Completed'), ('Non-Completed')")

    # Ensure the special folders are ordered first
    cursor.execute("UPDATE folders SET folder_order = 0 WHERE name = 'Pinned'")
    cursor.execute("UPDATE folders SET folder_order = 1 WHERE name = 'Non-Completed'")
    cursor.execute("UPDATE folders SET folder_order = 2 WHERE name = 'Completed'")

    # Assign order values to other folders starting from 3
    cursor.execute("""
        SELECT name FROM folders
        WHERE name NOT IN ('Pinned', 'Non-Completed', 'Completed')
        ORDER BY name
    """)
    other_folders = cursor.fetchall()
    for i, (name,) in enumerate(other_folders, start=3):
        cursor.execute("UPDATE folders SET folder_order = ? WHERE name = ?", (i, name))

    conn.commit()
    conn.close()

class DraggableFolder(RelativeLayout):
    def __init__(self, folder_name, icon_path, app_ref, **kwargs):
        super().__init__(size_hint_y=None, height=60, **kwargs)
        self.folder_name = folder_name
        self.app_ref = app_ref
        self.dragging = False

        layout = BoxLayout(orientation='horizontal', spacing=10, padding=(10, 10))

        if icon_path:
            icon = Image(source=icon_path, size_hint=(None, 1), width=30)
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
            self.velocity *= 0.02  # friction

            if abs(self.velocity) < 0.001:
                return False
        Clock.schedule_interval(flick, 1 / 60.)

class CircleButton(Button):
    def __init__(self, app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = app_ref

        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0, 0, 0, 0)  # Fully transparent
        self.is_hovered = False

        with self.canvas.before:
            self.fill_color = Color(0, 0, 0, 1)  # Placeholder, will be set later
            self.fill_circle = Ellipse(pos=self.pos, size=self.size)

            self.stroke_color = Color(1, 1, 1, 1)  # Placeholder, will be set later
            self.stroke_circle = Line(circle=(self.center_x, self.center_y, self.width / 2), width=3)

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
            min(self.width, self.height) / 2 - 2
        )

class FolderButton(RelativeLayout):
    def __init__(self, text, icon_path=None, app_ref=None, **kwargs):
        super().__init__(size_hint_y=None, height=60, **kwargs)

        layout = BoxLayout(orientation='horizontal', spacing=10, padding=(10, 10))

        if icon_path:
            icon = Image(source=icon_path, size_hint=(None, 1), width=30)
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

class DraggableReminder(BoxLayout):
    def __init__(self, reminder_text, urgency_level, folder_name, app_ref, **kwargs):
        super().__init__(orientation='horizontal',
                         size_hint=(None, None),
                         size=(750, 55),
                         spacing=10,
                         padding=(5, 5),
                         **kwargs)
        self.app_ref = app_ref
        self.reminder_text = reminder_text
        self.folder_name = folder_name
        self.dragging = False


        # Add complete circle button
        # Add complete circle button (and pass app_ref!)
        self.complete_btn = CircleButton(app_ref=self.app_ref, size_hint=(None, None), size=(40, 40))
        self.complete_btn.bind(on_press=lambda instance: self.app_ref.mark_as_completed(reminder_text, folder_name))
        self.add_widget(self.complete_btn)

        # Add image based on urgency level (skip if level 1)
        if urgency_level == 2:
            self.urgency_image = Image(
                source='/Users/Andrew2/PycharmProjects/Reminders_App/Whole App Files/Main Scripts/Images for App/lvl1.png',
                size_hint=(None, 1),
                width=30
            )
            self.add_widget(self.urgency_image)

        elif urgency_level == 3:
            self.urgency_image = Image(
                source='/Users/Andrew2/PycharmProjects/Reminders_App/Whole App Files/Main Scripts/Images for App/lvl2.png',
                size_hint=(None, 1),
                width=30
            )
            self.add_widget(self.urgency_image)

        self.text_btn = HoverButton(
            text=reminder_text,
            size_hint=(1, 1),
            background_normal='',
            background_color=self.app_ref.theme.get("primary", (0.5, 0.5, 0.5, 1)),
            app_ref=self.app_ref
        )
        self.text_btn.color = self.app_ref.theme.get("text", (1, 1, 1, 1))
        self.add_widget(self.text_btn)

    def update_bg_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

        # Make draggable
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

        setup_database()  # Set up the DB just once at app init

        # Load theme before UI builds
        self.load_last_theme()

        #  Fallback if no theme was loaded
        if not hasattr(self, "theme"):
            self.theme = {
                "background": (0.204, 0.208, 0.212, 1),
                "primary": (0.239, 0.059, 0.349, 1),
                "secondary": (0.086, 0.616, 0.651, 1),
                "text": (1, 1, 1, 1)
            }
    def build(self):
        self.title = "Reminders App"


        # Fallback in case load failed
        if not hasattr(self, "theme"):
            self.theme = {
                "background": (0.204, 0.208, 0.212, 1),
                "primary": (0.239, 0.059, 0.349, 1),
                "secondary": (0.086, 0.616, 0.651, 1),
                "text": (1, 1, 1, 1)
            }

        self.root_layout = FloatLayout()

        with self.root_layout.canvas.before:
            self.bg_color = Color(*self.theme["background"])
            self.bg_rect = Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)
            self.border_color = Color(*self.theme["secondary"])
            self.full_border = Line(width=14, rectangle=(0, 0, 0, 0))

        self.root_layout.bind(pos=self.update_layout, size=self.update_layout)

        self.main_layout = BoxLayout(orientation='horizontal', spacing=10, padding=10, size_hint=(1, 1))
        self.root_layout.add_widget(self.main_layout)

        with self.main_layout.canvas.after:
            self.divider_color = Color(*self.theme["secondary"])
            self.divider_line_left = Line(width=8)
            self.divider_line_right = Line(width=8)

        self.main_layout.bind(pos=self.update_layout, size=self.update_layout)

        # Add your full UI setup (e.g. sidebar, button wrapper, etc.)
        self.setup_ui()
        self.apply_theme()
        return self.root_layout

    def update_layout(self, *args):
        self.bg_rect.pos = self.root_layout.pos
        self.bg_rect.size = self.root_layout.size
        self.full_border.rectangle = (
            self.root_layout.x, self.root_layout.y,
            self.root_layout.width, self.root_layout.height
        )

        # Divider positions
        left_divider_x = 285
        right_divider_x = 1090
        y = self.main_layout.y
        height = self.main_layout.height
        self.divider_line_left.points = [left_divider_x, y, left_divider_x, y + height]
        self.divider_line_right.points = [right_divider_x, y, right_divider_x, y + height]

    def update_full_border(self, instance, value):
        self.full_border.rectangle = (instance.x, instance.y, instance.width, instance.height)

    def update_content_border(self, instance, value):
        self.content_border.rectangle = (instance.x, instance.y, instance.width, instance.height)

    def mark_as_completed(self, reminder_text, current_folder):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. Delete this reminder from every folder *except* Completed
        cursor.execute("""
            DELETE FROM reminders
            WHERE text = ? AND folder_name != 'Completed'
        """, (reminder_text,))

        # 2. Insert into Completed if not already there
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

        # 3. Reload the current folder
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
        new_order = []
        for widget in self.sidebar.children[::-1]:  # top-to-bottom
            if isinstance(widget, DraggableFolder):
                new_order.append(widget.folder_name)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for i, folder_name in enumerate(new_order):
            cursor.execute("""
                UPDATE folders
                SET folder_order = ?
                WHERE name = ?
            """, (i, folder_name))
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
            text='',
            size_hint_y=None,
            height=1000,  # Adjust the height so it creates a scrollable area
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
            size=(800, 600),
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
        self.selected_folder = None  # Ensures this is always available

        # Main content area
        content_frame = FloatLayout(size_hint=(0.6, 1))  # 60% width, full height

        # Create a centered box inside the content frame to wrap the label
        content_box = BoxLayout(size_hint=(1, 0.9), pos_hint={'center_x': 0.53, 'center_y': 0.5})

        self.reminder_area = FlickScrollView(
            size_hint=(1, 1),
            bar_width=20,
            scroll_type=['bars', 'content'],
            bar_color=(0.5, 0.5, 0.5, 0.8),
            bar_inactive_color=(0.3, 0.3, 0.3, 0.4),
            scroll_timeout=150
        )

        self.viewing_label = Label(
            text='[b]Select a folder to view reminders[/b]',
            markup=True,
            font_size=50,
            size_hint=(1, None),
            height=500,
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

        # Button Column
        # Right Column Wrapper
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
            text='[b]Help[/b]', markup=True,
            background_normal='', background_color=self.theme["primary"],
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

        # Add layout inside wrapper, then to main app layout
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

        with self.root_layout.canvas.before:
            self.bg_color = Color(*self.theme["background"])  # Store for later update
            self.bg_rect = Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)

            self.border_color_box = Color(*self.theme["secondary"])
            self.full_border = Line(width=14, rectangle=(0, 0, 0, 0))  # Init with empty box

        with self.main_layout.canvas.after:
            self.divider_color = Color(*self.theme["secondary"])  # Store this too!
            self.divider_line_left = Line(width=8)
            self.divider_line_right = Line(width=8)

        with self.main_layout.canvas.after:
            self.border_color_line = Color(*self.theme["secondary"])
            self.divider_line_left = Line(width=8)
            self.divider_line_right = Line(width=8)  # Divider between middle and right columns

        def update_divider_lines(*args):
            # The left divider line sits at the right edge of the ScrollView (the left column)

            left_offset = 285  # Moves the left divider 5 pixels to the left
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

        # Placeholder for themes (empty for now)
        mock_saved_themes = []

        if not mock_saved_themes:
            self.saved_themes_box.add_widget(Label(
                text="No Saved Themes",
                size_hint_y=None,
                height=40,
                halign='center'
            ))
        else:
            for theme in mock_saved_themes:
                btn = HoverButton(
                    text=f"[b]{theme['name']}[/b]",
                    markup=True,
                    size_hint_y=None,
                    height=40,
                    background_normal='',
                    background_color=self.theme["primary"],
                    app_ref=self
                )
                btn.bind(on_press=lambda inst, t=theme: self.load_custom_theme(t))
                self.saved_themes_box.add_widget(btn)

        scroll.add_widget(self.saved_themes_box)
        layout.add_widget(scroll)

        # --- Mode Buttons (Dark / Light / Custom / Save) ---
        dark_btn = Button(text="Dark Mode", size_hint_y=None, height=50)
        light_btn = Button(text="Light Mode", size_hint_y=None, height=50)
        custom_btn = Button(text="Custom Colors", size_hint_y=None, height=50)
        save_btn = Button(text="Save Theme", size_hint_y=None, height=50)

        dark_btn = HoverButton(
            text="[b]Dark Mode[/b]", markup = True, size_hint_y=None, height=50,
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
            text="[b]Custom Colors[/b]", markup = True, size_hint_y=None, height=50,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )
        save_btn = HoverButton(
            text="[b]Save Theme[/b]", markup = True, size_hint_y=None, height=50,
            background_normal='', background_color=self.theme["primary"],
            app_ref=self
        )

        for btn in [dark_btn, light_btn, custom_btn, save_btn]:
            layout.add_widget(btn)

        popup = Popup(
            title="Choose Theme",
            content=layout,
            size_hint=(None, None),
            size=(650, 550),
            auto_dismiss=True
        )
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

        # Reapply theme to current folder’s reminders
        if hasattr(self, "selected_folder") and self.selected_folder:
            folder_name = self.selected_folder.replace('[b]', '').replace('[/b]', '')
            self.load_reminders(folder_name)


    def load_last_theme(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT background, "primary", "secondary", "text" FROM themes ORDER BY id DESC LIMIT 1'
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

    def save_theme_to_db(self, instance=None):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Delete previous saved theme if you want to keep only 1 (optional)
        cursor.execute("DELETE FROM themes")

        cursor.execute('''
            INSERT INTO themes (background, "primary", "secondary", "text")
            VALUES (?, ?, ?, ?)
        ''', (
            self.rgba_to_hex(self.theme["background"]),
            self.rgba_to_hex(self.theme["primary"]),
            self.rgba_to_hex(self.theme["secondary"]),
            self.rgba_to_hex(self.theme["text"])
        ))

        conn.commit()
        conn.close()

    def clear_completed_reminders(self, instance):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reminders WHERE folder_name = 'Completed'")
        conn.commit()
        conn.close()

        # Refresh only if we're currently viewing Completed
        if self.selected_folder and 'Completed' in self.selected_folder:
            self.load_reminders("Completed")

    def reorder_folders(self):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Reverse the list since Kivy StackLayout children are in reverse order
        visible_folders = [child for child in self.sidebar.children if isinstance(child, DraggableFolder)]
        visible_folders = visible_folders[::-1]

        for i, widget in enumerate(visible_folders):
            cursor.execute("""
                UPDATE folders
                SET folder_order = ?
                WHERE name = ?
            """, (i, widget.folder_name))

        conn.commit()
        conn.close()

        # Reload in new order
        self.load_folders()

    def load_folders(self):
        self.sidebar.clear_widgets()
        self.sidebar_buttons.clear()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name, folder_order FROM folders")
        folders = cursor.fetchall()

        # Custom sort: Pinned, Non-Completed, Completed always on top
        priority = {'Pinned': 0, 'Non-Completed': 1, 'Completed': 2}
        folders.sort(key=lambda x: (priority.get(x[0], 3), x[1]))
        conn.close()

        for folder in folders:
            name = folder[0]

            if name == "Completed":
                icon_path = "Images for App/check.png"
            elif name == "Non-Completed":
                icon_path = "Images for App/incomplete.png"
            elif name == "Pinned":
                icon_path = "Images for App/pinned.png"
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

    def change_folder_icon(self, instance):
        if not self.selected_folder:
            popup = Popup(title="No Folder Selected",
                          content=Label(text="Please select a folder to change the icon"),
                          size_hint=(None, None), size=(670, 200))
            popup.open()
            return

        folder_name = self.selected_folder.replace('[b]', '').replace('[/b]', '')
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        # Drop zone / preview image
        self.drop_preview = Image(
            source='Assets/anything.png',  # default preview
            allow_stretch=True,
            size_hint=(1, 0.7)
        )
        layout.add_widget(self.drop_preview)

        # FileChooser
        filechooser = FileChooserIconView(size_hint=(1, 0.8))
        layout.add_widget(filechooser)

        # Update button
        update_btn = Button(
            text="Update Icon",
            size_hint=(1, 0.2),
            background_color=self.theme["primary"]
        )
        layout.add_widget(update_btn)

        popup = Popup(
            title=f"Change Icon for: {folder_name}",
            content=layout,
            size_hint=(None, None),
            size=(800, 600)
        )
        popup.open()

        def on_selection(_, selected):
            if selected:
                self.drop_preview.source = selected[0]  # Preview selected image

        filechooser.bind(selection=on_selection)

        def on_update_pressed(_):
            selected = filechooser.selection
            if selected:
                self.update_folder_icon(selected, folder_name)
                popup.dismiss()

        update_btn.bind(on_press=on_update_pressed)

    def update_folder_icon(self, selection, folder_name):
        if selection:
            file_path = selection[0]
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

        # Show "Clear Completed" only for Completed folder
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

        # Fetch reminders from DB
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT text, urgency_level FROM reminders WHERE folder_name = ? ORDER BY reminder_order ASC",
                       (folder_name_clean,))
        reminders = cursor.fetchall()
        conn.close()

        # Show "No reminders" message if empty
        if not reminders:
            self.viewing_label.text = f"[b]No reminders in '{folder_name_clean}'[/b]"
            self.reminder_area_layout.add_widget(self.viewing_label)
            return

        # Otherwise, build reminder widgets
        for text, urgency in reminders:
            show_urgency = folder_name_clean != "Completed"
            btn = DraggableReminder(
                reminder_text=text,
                urgency_level=urgency if show_urgency else None,
                folder_name=folder_name_clean,
                app_ref=self
            )
            self.reminder_list.add_widget(btn)

        self.reminder_area_layout.add_widget(self.reminder_list)

    def add_reminder(self, instance):
        if not self.selected_folder:
            popup = Popup(title="No Folder Selected",
                          content=Label(text="Please select a folder first."),
                          size_hint=(None, None), size=(400, 200))
            popup.open()
            return

        folder_clean = self.selected_folder.replace('[b]', '').replace('[/b]', '')

        if folder_clean == "Completed":
            popup = Popup(title="Invalid Folder",
                          content=Label(text="Cannot Add To Completed folder."),
                          size_hint=(None, None), size=(700, 400))
            popup.open()
            return

        # Layout with urgency spinner
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        text_input = TextInput(hint_text="Reminder text", multiline=False, size_hint=(1, 0.5))
        urgency_spinner = Spinner(
            text='No Urgency',
            values=('No Urgency', 'Medium', 'High'),
            size_hint=(1, 0.5)
        )
        add_button = Button(
            text="Add Reminder",
            size_hint=(1, 0.5),
            background_color=self.theme["primary"]
        )

        layout.add_widget(text_input)
        layout.add_widget(urgency_spinner)
        layout.add_widget(add_button)

        popup = Popup(title="New Reminder", content=layout, size_hint=(None, None), size=(600, 400))
        popup.open()
        Clock.schedule_once(lambda dt: setattr(text_input, 'focus', True), 0.1)

        def on_add(_):
            reminder_text = text_input.text.strip()

            urgency_map = {
                'No Urgency': 1,
                'Medium': 2,
                'High': 3
            }
            urgency_level = urgency_map.get(urgency_spinner.text, 1)  # Default to 1

            if reminder_text:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                # Get next order
                cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = ?", (folder_clean,))
                max_order = cursor.fetchone()[0]
                next_order = (max_order + 1) if max_order is not None else 0

                # Insert into selected folder
                cursor.execute("""
                    INSERT INTO reminders (text, folder_name, reminder_order, urgency_level)
                    VALUES (?, ?, ?, ?)
                """, (reminder_text, folder_clean, next_order, urgency_level))

                # Insert into Non-Completed (optional)
                if folder_clean != "Non-Completed":
                    cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = 'Non-Completed'")
                    max_nc_order = cursor.fetchone()[0]
                    next_nc_order = (max_nc_order + 1) if max_nc_order is not None else 0

                    cursor.execute("""
                        INSERT INTO reminders (text, folder_name, reminder_order, urgency_level)
                        VALUES (?, 'Non-Completed', ?, ?)
                    """, (reminder_text, next_nc_order, urgency_level))

                conn.commit()
                conn.close()
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
        self.apply_theme()
        self.save_theme_to_db()

    def set_light_theme(self, instance=None):
        self.theme = {
            "background": (0.91, 0.902, 0.875, 1),  # dirty white
            "primary": (0.255, 0.588, 0.384, 1),  # spring green
            "secondary": (0.176, 0.176, 0.231, 1),  # arctic black/blue
            "text": (0, 0, 0, 1)  # black text
        }
        self.apply_theme()
        self.save_theme_to_db()

    def save_theme_to_db(self, instance=None):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        theme_name = "Default Theme"

        def to_hex(rgba):
            return '#{:02x}{:02x}{:02x}'.format(
                int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255)
            )

        cursor.execute("""
            INSERT INTO themes (background, "primary", "secondary", "text")
            VALUES (?, ?, ?, ?)
        """, (
            to_hex(self.theme["background"]),
            to_hex(self.theme["primary"]),
            to_hex(self.theme["secondary"]),
            to_hex(self.theme["text"])
        ))

        conn.commit()
        conn.close()

    def load_custom_theme(self, theme_dict):
        self.theme = {
            "background": theme_dict["background"],
            "primary": theme_dict["primary"],
            "secondary": theme_dict["secondary"]
        }
        self.apply_theme()

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
            Color(*self.theme["secondary"])  # Use the app's theme secondary color
            btn.circle = Ellipse(pos=btn.pos, size=btn.size)

        def update_circle(instance, value):
            btn.circle.pos = btn.pos
            btn.circle.size = btn.size

        btn.bind(pos=update_circle, size=update_circle)

        return btn


# Runs the script
if __name__ == "__main__":
    setup_database()
    RemindersApp().run()
