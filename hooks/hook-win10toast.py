# PyInstaller hook for win10toast
# This ensures win10toast data files are properly included

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# Collect all data files from win10toast package
datas = collect_data_files('win10toast')

# Copy metadata to help pkg_resources find the package
datas += copy_metadata('win10toast')

# pkg_resources.py2_warn removed: module does not exist in newer setuptools (avoids "hidden import not found" warning)
hiddenimports = []
