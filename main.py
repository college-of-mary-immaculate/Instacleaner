import os
import ctypes
from ctypes import wintypes
import shutil
import concurrent.futures
import subprocess
import sys
import pyuac
import pystray
from PIL import Image
from io import BytesIO
from urllib import request
import time
import threading

class InstaCleaner:
    def __init__(self):
        self.auto_clean_interval = 60  # Increase the interval to reduce frequency
        self.total_spaces = None
        self.free_spaces = None
        self.one_percent = None

    def start_cleaning(self):
        self.clean_trash()
        self.clean_temp_files()

    def get_disk_usage(self):
        try:
            disk_usage = shutil.disk_usage('/')
            self.total_spaces = disk_usage.total / (1024 ** 3)  # GB
            self.free_spaces = disk_usage.free / (1024 ** 3)  # GB
            self.one_percent = (1 / 100) * self.total_spaces
        except Exception as e:
            print(f"Failed to get disk usage: {str(e)}")

    def get_directory_size(self, directory):
        total_size = 0
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total_size += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            total_size += self.get_directory_size(entry.path)
                    except (PermissionError, FileNotFoundError):
                        pass
        except (PermissionError, FileNotFoundError):
            pass
        return total_size

    def get_recycle_bin_size(self):
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("i64Size", ctypes.c_int64),
                        ("i64NumItems", ctypes.c_int64)]

        query_info = SHQUERYRBINFO()
        query_info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(query_info))

        if result == 0:
            return query_info.i64Size / (1024 ** 3)  # GB
        else:
            print("Failed to get Recycle Bin size")
            return 0

    def get_total_temp_files_size(self):
        temp_directories = [os.getenv('TEMP'), os.path.join(os.getenv('WINDIR'), 'Temp')]
        total_temp_size = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = executor.map(self.get_directory_size, filter(os.path.exists, temp_directories))

        return sum(results) / (1024 ** 3)  # Convert bytes to GB

    def monitor_sizes(self):
        self.get_disk_usage()
        while True:
            print("Monitoring sizes...")  # for debugging
            total_temp_size = self.get_total_temp_files_size()
            total_recsize = self.get_recycle_bin_size()

            total_trash_size = total_temp_size + total_recsize
            print(f"Total trash size: {total_trash_size:.2f} GB")

            if total_trash_size >= self.one_percent:
                self.start_cleaning()

            else:
                print("Not yet!")

            print(f"Sleeping for {self.auto_clean_interval} seconds...")  # for debugging
            time.sleep(self.auto_clean_interval)

    def clean_trash(self):
        try:
            ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 3)
            print("Recycle Bin has been emptied successfully!")
        except Exception as e:
            print(f"Failed to empty Recycle Bin: {str(e)}")

    def clean_temp_files(self):
        temp_directories = [os.getenv('TEMP'), os.path.join(os.getenv('WINDIR'), 'Temp')]

        for directory in temp_directories:
            if directory and os.path.exists(directory):
                for root, _, files in os.walk(directory):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            print(f"Failed to delete {file_path}: {str(e)}")
        
        print("Temporary files cleaned.")

def add_scheduled_task():
    try:
        task_name = "InstaCleaner_AutoStart"
        script_path = os.path.realpath(sys.argv[0])
        user = os.getenv("USERNAME")

        command = f'schtasks /create /tn "{task_name}" /tr "{script_path}" /sc onlogon /rl highest /f /ru {user}'
        subprocess.run(command, shell=True, check=True)
        print("Scheduled task created successfully!")
    except subprocess.CalledProcessError as e:
        print(f"Error creating scheduled task: {e.stderr.decode()}")

def fetch_image(image_path_or_url):
    try:
        if os.path.exists(image_path_or_url):
            return Image.open(image_path_or_url)
        
        response = request.urlopen(image_path_or_url)
        return Image.open(BytesIO(response.read()))

    except (request.URLError, IOError) as e:
        print(f"Error fetching image: {e}")
        return None

def on_quit(icon, item):
    icon.stop()

def main():
    if not pyuac.isUserAdmin():
        pyuac.runAsAdmin()
    else: 
        add_scheduled_task()
        cleaner = InstaCleaner()

        image_source = os.path.join(os.path.dirname(__file__), 'assets', 'transparent_logo_250x250.ico')

        image = fetch_image(image_source)

        if image is None:
            image_url = "https://res.cloudinary.com/izynegallardo/image/upload/v1725017419/transparent_logo_250x250_jzz5en.png"
            image = fetch_image(image_url)
        
        if image is None:
            image = Image.new('RGB', (64, 64), color='black')

        icon = pystray.Icon("InstaCleaner", image, "InstaCleaner", menu=pystray.Menu(
            pystray.MenuItem("Clean now", lambda: cleaner.start_cleaning()),
            pystray.MenuItem("Quit", on_quit)
        ))

        monitoring_thread = threading.Thread(target=cleaner.monitor_sizes, daemon=True)
        monitoring_thread.start()

        icon.run()

if __name__ == "__main__":
    main()