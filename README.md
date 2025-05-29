# TaskReminder-App

This is my first large-scale, solo, unguided Python project. It uses the **Kivy** framework and links with a created **SQLite database** to keep reminders organized.

I am working on making it available on the App Store.

The final version is **1.18**, and I have provided 4 previous scripts if you want to see progress stages. Please reach out and ask questions — I would love to help anyone if I am able to. I have tried to include as many comments as possible to help any viewers.

---

### Installation Instructions

1. To install as a standalone app please refer to instructions below, if you don't mind launching via terminal, continue here.
2. Paste in these commands
```bash
git clone https://github.com/atimmeny27/TaskReminder-App)
cd TaskReminder-App
```

3. Type in "ls" make sure you see main.py popup in the list
4. To launch, type ```python3 main.py```
5. This will still persist the sql database and notifications across separate launches.

## Optional
1. To add to desktop without an application, you can run a shell script through automator.

### Download

Download the latest version of TaskReminders for macOS here:

[**Click to Download TaskReminders**](https://github.com/atimmeny27/TaskReminder-App/releases/latest/download/TaskReminders.app.zip)

---

### Installation Instructions for standalone app (macOS only)

After downloading:

1. This is a **Mac-only** app. Make sure the `.zip` file is in your **Downloads** folder in Finder.  
   (If an app is already created, you can delete it for now — only the `.zip` is needed.)
   (If no .zip is created and only the app is, this is fine just look at step 6)

3. Open **Terminal** through the Applications > Utilities folder,  
   **or** press `⌘ (command) + Spacebar` to open Spotlight and search for **Terminal**.

4. Once Terminal is open (and assuming you haven't renamed or moved the `.zip` file from Downloads):

5. Paste the following command into Terminal removing ** YourUsernameHere ** and putting in your own:

   ```bash
   sudo xattr -d com.apple.quarantine /Users/**YourUsernameHere**/Downloads/TaskReminders.app.zip


 6.If only an app was created and no .zip, just delete .zip from the end of the command and keep .app

7. Hint, your username if you aren't sure will be here in the terminal "YourUsername@MacBook-Air ~ $"
10. This command will remove the auto generated quarantine attributes with "xattr -d" since this is only a web app right now
11. This command requires admin privelages through "sudo", so enter your password to confirm

12. Instead, you can also paste "sudo xattr -d" then drag the .zip file into the terminal to get the exact file path 
13. Once this is done, you can click on the .zip file to create a functioning application
14. Read through the in-app help section to get started
15. You can also safely delete the .zip file from downloads
   
    (Optional) Open finder and drag the app from Downloads to Applications to add to app library

[Video Tutorial coming soon]()
