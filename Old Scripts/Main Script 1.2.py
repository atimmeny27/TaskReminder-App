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
    cursor.execute("INSERT OR IGNORE INTO folders (name) VALUES ('Completed'), ('Non-Completed')")
    conn.commit()
    conn.close()

# Kivy App Class
class RemindersApp(App):
    def build(self):
        self.title = "Reminders App"
        self.setup_ui()
        return self.main_layout

    def setup_ui(self):
        self.main_layout = BoxLayout(orientation='horizontal', spacing=10, padding=10)

        # Sidebar
        self.sidebar = BoxLayout(orientation='vertical', size_hint=(0.2, 1))
        self.sidebar_buttons = []
        self.main_layout.add_widget(self.sidebar)

        # Main content area
        self.content = Label(text='[b]Select a folder to view reminders[/b]',
                             markup=True,
                             halign='center',
                             valign='middle',
                             font_size=55)
        self.content.size_hint = (0.6, 1)
        self.content.bind(size=self.content.setter('text_size'))
        self.main_layout.add_widget(self.content)

        # Button Column
        button_layout = BoxLayout(orientation='vertical', size_hint=(0.2, 1), spacing=25)

        self.add_folder_btn = Button(text='[b]Add Folder[/b]', markup=True,
                                     background_normal='', background_color=(0.047, 0.42, 0.44, 1))
        self.delete_folder_btn = Button(text='[b]Delete Folder[/b]', markup=True,
                                        background_normal='', background_color=(0.239, 0.059, 0.349, 1))
        self.change_icon_btn = Button(text='[b]Change Folder Icon[/b]', markup=True,
                                      background_normal='', background_color=(0.024, 0.286, 0.388, 1))

        self.add_folder_btn.bind(on_press=self.add_folder)
        self.delete_folder_btn.bind(on_press=self.delete_folder)
        self.change_icon_btn.bind(on_press=self.change_folder_icon)

        button_layout.add_widget(self.add_folder_btn)
        button_layout.add_widget(self.delete_folder_btn)
        button_layout.add_widget(self.change_icon_btn)

        self.main_layout.add_widget(button_layout)

        self.load_folders()

    def load_folders(self):
        self.sidebar.clear_widgets()
        self.sidebar_buttons.clear()

        conn = sqlite3.connect("reminders.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM folders")
        folders = cursor.fetchall()
        conn.close()

        for folder in folders:
            btn = Button(text=folder[0], size_hint_y=None, height=40)
            btn.bind(on_press=self.switch_view)
            self.sidebar_buttons.append(btn)
            self.sidebar.add_widget(btn)

    def add_folder(self, instance):
        popup = Popup(title="New Folder", content=TextInput(hint_text="Enter folder name"), size_hint=(None, None),
                      size=(400, 200))
        popup.open()
        text_input = popup.content
        text_input.bind(on_text_validate=self.add_folder_from_input)

    def add_folder_from_input(self, instance):
        folder_name = instance.text
        if folder_name:
            conn = sqlite3.connect("reminders.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO folders (name) VALUES (?)", (folder_name,))
            conn.commit()
            conn.close()
            self.load_folders()

    def delete_folder(self, instance):
        if self.sidebar_buttons:
            selected_item = self.sidebar_buttons[0].text
            if selected_item in ["Completed", "Non-Completed"]:
                popup = Popup(title="Delete Folder",
                              content=Label(text=f"{selected_item} cannot be deleted\nPermanent folder"),
                              size_hint=(None, None), size=(400, 200))
                popup.open()
            else:
                conn = sqlite3.connect("reminders.db")
                cursor = conn.cursor()
                cursor.execute("DELETE FROM folders WHERE name = ?", (selected_item,))
                conn.commit()
                conn.close()
                self.load_folders()

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

    def switch_view(self, instance):
        folder_name = instance.text
        self.content.text = f"Viewing: {folder_name}"

# Run the app
if __name__ == "__main__":
    setup_database()
    RemindersApp().run()