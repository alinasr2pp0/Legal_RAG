@echo off
set PYTHONPATH=src
python scripts\data\build_index.py --input data\processed\chunks.json --recreate