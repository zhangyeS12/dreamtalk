"""Bundle only resources used by the local jieba search tokenizer."""

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("jieba", includes=["dict.txt", "finalseg/*.p"])
