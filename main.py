import sys

if __name__ == "__main__":
    if "--clasica" in sys.argv:  # Interfaz anterior (CustomTkinter), por si se necesita mientras tanto.
        from finanzas.ui.app import main
    else:
        from finanzas.ui_flet.app import main
    main()
