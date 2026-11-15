import sys, traceback

try:
    import main
    main.main()
except SystemExit:
    pass
except BaseException:
    traceback.print_exc()
    print("\nChessHelper crashed. Copy the text above.")
    input("Press Enter to close...")