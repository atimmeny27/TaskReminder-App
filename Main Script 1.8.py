import sqlite3
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

# Database Setup
def setup_database():
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        image_path TEXT DEFAULT ''
    )''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        folder_name TEXT NOT NULL
    )''')

    # Add 'reminder_order' column if it doesn't exist
    cursor.execute("PRAGMA table_info(reminders)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'reminder_order' not in columns:
        cursor.execute("ALTER TABLE reminders ADD COLUMN reminder_order INTEGER DEFAULT 0")

    cursor.execute("INSERT OR IGNORE INTO folders (name) VALUES ('Pinned'), ('Completed'), ('Non-Completed')")
    conn.commit()
    conn.close()

class HoverButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(mouse_pos=self.on_mouse_pos)
        self.default_color = ((0.239, 0.059, 0.349, 1))
        self.hover_color = (0.086, 0.616, 0.651, 1)
        self.background_normal = ''
        self.background_color = self.default_color

    def on_mouse_pos(self, *args):
        if not self.get_root_window():
            return  # Widget not in the UI yet

        pos = args[1]
        inside = self.collide_point(*self.to_widget(*pos))
        self.background_color = self.hover_color if inside else self.default_color

class CircleButton(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_down = ''
        self.background_color = (0, 0, 0, 0)  # Transparent background

        self.border_color = (0.086, 0.616, 0.651, 1)  # Blue border
        self.fill_color = (0.2, 0.2, 0.2, 1)          # Gray-ish fill
        self.hover_color = (0.1, 0.7, 0.8, 1)         # Hover border color

        self.is_hovered = False

        with self.canvas.before:
            self.fill = Color(*self.fill_color)
            self.fill_circle = Ellipse(pos=self.pos, size=self.size)

            self.stroke = Color(*self.border_color)
            self.stroke_circle = Line(circle=(self.center_x, self.center_y, self.width/2), width=3)

        self.bind(pos=self.update_graphics, size=self.update_graphics)
        Window.bind(mouse_pos=self.on_mouse_pos)

    def on_mouse_pos(self, *args):
        if not self.get_root_window():
            return
        pos = args[1]
        inside = self.collide_point(*self.to_widget(*pos))
        if self.is_hovered != inside:
            self.is_hovered = inside
            self.update_graphics()

    def update_graphics(self, *args):
        self.fill_circle.pos = self.pos
        self.fill_circle.size = self.size

        self.stroke_circle.circle = (
            self.center_x, self.center_y, min(self.width, self.height) / 2 - 2
        )

        # Update stroke color on hover
        self.stroke.rgba = self.hover_color if self.is_hovered else self.border_color

class FolderButton(RelativeLayout):
    def __init__(self, text, icon_path=None, **kwargs):
        super().__init__(size_hint_y=None, height=60, **kwargs)

        layout = BoxLayout(orientation='horizontal', spacing=10, padding=(10, 10))

        if icon_path:
            icon = Image(source=icon_path, size_hint=(None, 1), width=30)
            layout.add_widget(icon)

        label = HoverButton(
            text=f"[b]{text}[/b]",
            markup=True,
            background_normal='',
            background_color=(0.239, 0.059, 0.349, 1)
        )
        self.label = label  # Store for binding
        layout.add_widget(label)

        self.add_widget(layout)

class DraggableReminder(BoxLayout):
    def __init__(self, reminder_text, folder_name, app_ref, **kwargs):
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

        # Circle button on the left
        self.complete_btn = CircleButton(size_hint=(None, None), size=(40, 40))
        self.complete_btn.bind(on_press=lambda instance: self.app_ref.mark_as_completed(reminder_text, folder_name))

        # Hover-style reminder label
        self.text_btn = HoverButton(
            text=reminder_text,
            size_hint=(1, 1),
            background_normal='',
            background_color=(0.239, 0.059, 0.349, 1)
        )

        self.add_widget(self.complete_btn)
        self.add_widget(self.text_btn)

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

            # Make a copy of current visible order (bottom-to-top)
            siblings = parent.children[:]
            siblings.reverse()

            # Remove self from the copy
            if self in siblings:
                siblings.remove(self)

            # Calculate insertion index by comparing Y positions
            insertion_index = 0
            for i, widget in enumerate(siblings):
                if widget.y < self.y:
                    insertion_index = i + 1

            # Insert self at the new position
            siblings.insert(insertion_index, self)

            # Clear and re-add all widgets in new order
            parent.clear_widgets()
            for widget in siblings:
                parent.add_widget(widget)

            # Update order in database
            self.app_ref.update_reminder_order(self.folder_name, self.reminder_text, insertion_index)

        return super().on_touch_up(touch)

class RemindersApp(App):
    def build(self):
        self.title = "Reminders App"
        self.setup_ui()
        return self.root_layout

    def update_full_border(self, instance, value):
        self.full_border.rectangle = (instance.x, instance.y, instance.width, instance.height)

    def update_content_border(self, instance, value):
        self.content_border.rectangle = (instance.x, instance.y, instance.width, instance.height)

    def mark_as_completed(self, reminder_text, current_folder):
        conn = sqlite3.connect("reminders.db")
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
        conn = sqlite3.connect("reminders.db")
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

    def reorder_reminders(self):
        if not self.selected_folder:
            return

        folder_clean = self.selected_folder.replace('[b]', '').replace('[/b]', '')
        conn = sqlite3.connect("reminders.db")
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


    def setup_ui(self):
        self.root_layout = FloatLayout()

        with self.root_layout.canvas.before:
            Color(0.204, 0.208, 0.212, 1)  # Background color #343536
            self.bg_rect = Rectangle(pos=self.root_layout.pos, size=self.root_layout.size)

            Color(0.047, 0.42, 0.44, 1)
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
        content_box = BoxLayout(size_hint=(0.9, 0.9), pos_hint={'center_x': 0.5, 'center_y': 0.5})

        self.reminder_area = ScrollView(size_hint=(1, 1))

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
        self.add_folder_btn = HoverButton(text='[b]Add Folder[/b]', markup=True,
                                     background_normal='', background_color=(0.239, 0.059, 0.349, 1))
        self.delete_folder_btn = HoverButton(text='[b]Delete Folder[/b]', markup=True,
                                        background_normal='', background_color=(0.239, 0.059, 0.349, 1))
        self.change_icon_btn = HoverButton(text='[b]Change Folder Icon[/b]', markup=True,
                                      background_normal='', background_color=(0.239, 0.059, 0.349, 1))
        self.add_reminder_btn = HoverButton(text='[b]Add Reminder[/b]',markup=True,
                                            background_normal='', background_color=(0.239, 0.059, 0.349, 1))
        self.add_reminder_btn.bind(on_press=self.add_reminder)

        # Bind actions
        self.add_folder_btn.bind(on_press=self.add_folder)
        self.delete_folder_btn.bind(on_press=self.delete_folder)
        self.change_icon_btn.bind(on_press=self.change_folder_icon)


        # Add each button with inner margin
        for btn in [self.add_folder_btn, self.delete_folder_btn, self.change_icon_btn, self.add_reminder_btn]:
            wrapper = BoxLayout(padding=(10, 5))
            wrapper.add_widget(btn)
            button_layout.add_widget(wrapper)

        # Add layout inside wrapper, then to main app layout
        button_wrapper.add_widget(button_layout)
        self.main_layout.add_widget(button_wrapper)


        # After adding your three columns (ScrollView, content Label, and button_wrapper)
        # add divider lines between the columns using canvas.after so they appear on top of your children
        with self.main_layout.canvas.after:
            Color(0.047, 0.42, 0.44, 1)  # Same color as your border
            self.divider_line_left = Line(width=8)  # Divider between left and middle columns
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

    def load_folders(self):
        self.sidebar.clear_widgets()
        self.sidebar_buttons.clear()

        conn = sqlite3.connect("reminders.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM folders")
        folders = cursor.fetchall()
        conn.close()

        folders.sort(key=lambda x: (x[0] != "Pinned", x[0]))

        for folder in folders:
            name = folder[0]

            if name == "Completed":
                icon_path = "Assets/check.png"
            elif name == "Non-Completed":
                icon_path = "Assets/incomplete.png"
            elif name == "Pinned":
                icon_path = "Assets/pinned.png"
            else:
                icon_path = "Assets/anything.png"

            folder_widget = FolderButton(name, icon_path=icon_path)
            folder_widget.label.bind(on_press=self.switch_view)

            self.sidebar_buttons.append(folder_widget.label)
            self.sidebar.add_widget(folder_widget)

        self.selected_folder = None

    def add_folder(self, instance):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)

        text_input = TextInput(hint_text="Enter folder name", multiline=False, size_hint=(1, 0.5))
        add_button = Button(text="Add", size_hint=(1, 0.5),
                            background_color=(0.239, 0.059, 0.349, 1))  # matches purple theme

        layout.add_widget(text_input)
        layout.add_widget(add_button)

        popup = Popup(title="New Folder", content=layout, size_hint=(None, None), size=(600, 400))
        popup.open()
        Clock.schedule_once(lambda dt: setattr(text_input, 'focus', True), 0.1)

        def on_add_button_pressed(_):
            folder_name = text_input.text.strip()
            if folder_name:
                conn = sqlite3.connect("reminders.db")
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
            background_color=(0.239, 0.059, 0.349, 1))

        btn_box = BoxLayout(spacing=10)
        btn_box.add_widget(confirm_btn)
        btn_box.add_widget(cancel_btn)
        layout.add_widget(btn_box)

        popup = Popup(title="Confirm Deletion", content=layout, size_hint=(None, None), size=(600, 300))
        popup.open()

        def on_confirm_delete(_):
            conn = sqlite3.connect("reminders.db")
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
        if self.sidebar_buttons:
            folder_name = self.sidebar_buttons[0].text
            filechooser = FileChooserIconView()
            filechooser.bind(on_selection=lambda instance, value: self.update_folder_icon(value, folder_name))

            popup = Popup(title="Select Image", content=filechooser, size_hint=(None, None), size=(800, 600))
            popup.open()

    def update_folder_icon(self, selection, folder_name):
        if selection:
            file_path = selection[0]
            conn = sqlite3.connect("reminders.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE folders SET image_path = ? WHERE name = ?", (file_path, folder_name))
            conn.commit()
            conn.close()
            self.load_folders()

    def load_reminders(self, folder_name):
        self.reminder_list.clear_widgets()

        # Hide the "Select a folder..." label if it's still showing
        if self.viewing_label in self.reminder_area_layout.children:
            self.reminder_area_layout.remove_widget(self.viewing_label)

        conn = sqlite3.connect("reminders.db")
        cursor = conn.cursor()
        cursor.execute("SELECT text FROM reminders WHERE folder_name = ? ORDER BY reminder_order ASC",
                       (folder_name,))
        reminders = cursor.fetchall()
        conn.close()

        if not reminders:
            self.viewing_label.text = f"[b]No reminders in '{folder_name}'[/b]"
            self.reminder_area_layout.add_widget(self.viewing_label)
            return  # Exit early so nothing else gets added

        for reminder in reminders:
            text = reminder[0]

            # Use the draggable button instead of a row layout
            btn = DraggableReminder(
                reminder_text=text,
                folder_name=folder_name,
                app_ref=self
            )

            self.reminder_list.add_widget(btn)

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

        layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        text_input = TextInput(hint_text="Reminder text", multiline=False, size_hint=(1, 0.5))
        add_button = Button(text="Add Reminder", size_hint=(1, 0.5),
                            background_color=(0.239, 0.059, 0.349, 1))

        layout.add_widget(text_input)
        layout.add_widget(add_button)

        popup = Popup(title="New Reminder", content=layout, size_hint=(None, None), size=(600, 400))
        popup.open()

        Clock.schedule_once(lambda dt: setattr(text_input, 'focus', True), 0.1)

        def on_add(_):
            reminder_text = text_input.text.strip()
            if reminder_text:
                conn = sqlite3.connect("reminders.db")
                cursor = conn.cursor()

                # Get the next reminder_order value for the selected folder
                cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = ?", (folder_clean,))
                max_order = cursor.fetchone()[0]
                next_order = (max_order + 1) if max_order is not None else 0

                # Insert into selected folder
                cursor.execute("""
                    INSERT INTO reminders (text, folder_name, reminder_order)
                    VALUES (?, ?, ?)
                """, (reminder_text, folder_clean, next_order))

                # If not already going into "Non-Completed", also insert it there
                if folder_clean != "Non-Completed":
                    cursor.execute("SELECT MAX(reminder_order) FROM reminders WHERE folder_name = 'Non-Completed'")
                    max_nc_order = cursor.fetchone()[0]
                    next_nc_order = (max_nc_order + 1) if max_nc_order is not None else 0

                    cursor.execute("""
                        INSERT INTO reminders (text, folder_name, reminder_order)
                        VALUES (?, 'Non-Completed', ?)
                    """, (reminder_text, next_nc_order))

                conn.commit()
                conn.close()
                popup.dismiss()
                self.load_reminders(folder_clean)

        add_button.bind(on_press=on_add)
        text_input.bind(on_text_validate=on_add)

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
            background_color=(0.086, 0.616, 0.651, 1),
        )
        btn.bind(on_press=lambda instance: self.mark_as_completed(reminder_text, folder_name))

        with btn.canvas.before:
            Color(*btn.background_color)
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