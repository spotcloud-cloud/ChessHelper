# ChessHelper

An automated computer-vision chess assistant built with Python, OpenCV, and Stockfish. ChessHelper reads the chessboard directly from your screen, analyzes the position using Stockfish, and helps identify optimal moves across different board styles.

## Features
- **Multi-Platform Board Styles:** Supports both **Chess.com** (`chesscom`) and **RoChess on Roblox** (`rochess`) with dedicated piece templates.
- **Screen Vision & Auto-Detection:** Uses `mss` and `OpenCV` (`cv2`) to capture the board and automatically detect board orientation (White or Black), with manual override options.
- **Stockfish Integration:** Connects directly to `stockfish.exe` via `python-chess` for move calculation and puzzle solving.
- **Customizable Controls:** Configure board styles, orientation, and emergency stop hotkeys via `config.json` or the built-in launcher.
- - **Puzzle & Auto Puzzle:** Views your screen to figure out the answer to the puzzle and automatically makes the move.

## Project Structure
- `main.py` – Core application loop, settings, and game mode logic (Start playing / Puzzle mode).
- `launcher.py` – Interface for configuring settings and launching the helper.
- `vision.py` & `calibrate.py` – Screen capture, board detection, and piece template matching.
- `config.json` – Stores user preferences such as `game_style`, `orientation`, and `stop_key`.
- `templates/` & `templates_rochess/` – Piece recognition image templates.

## Getting Started

### Option 1: Run the Executable (Windows)
1. Go to the Releases page and download ChessHelper.exe.
2. Run it. Stockfish and the piece templates are built in.
3. Pick a game and a mode, then press Start. It updates itself when a new release is out.

### Option 2: Run from Source
1. Clone the repository:
   ```bash
   git clone https://github.com
   cd ChessHelper
   ```
2. Install the required Python dependencies:
   ```bash
   pip install opencv-python numpy mss chess
   ```
3. Download the Windows binary from the [official Stockfish website](https://stockfishchess.org), rename it to `stockfish.exe`, and place it in the root directory of the project.
4. Run the program:
   ```bash
   python main.py
   ```
   
## Disclaimer
This tool is intended for educational purposes, personal coding practice, and offline/puzzle analysis. Please respect the terms of service of any platform you use. By using this in chess.com, you are vulnerable to be banned due to Chess.com' Fair Play Rule. Use legally.
