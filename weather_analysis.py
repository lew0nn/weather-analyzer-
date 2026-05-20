from ui import RequestWindow, ResultWindow


def main():
    try:
        result = RequestWindow().run()
        if result is not None:
            request, weather_table = result
            ResultWindow(request, weather_table).run()
    except Exception as error:
        print(f"\nError: {error}")


if __name__ == "__main__":
    main()
