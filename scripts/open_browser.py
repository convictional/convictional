import webbrowser

from config.settings import settings


def main() -> None:
    url = str(settings.base_url)
    print(url)
    webbrowser.open(url)


if __name__ == "__main__":
    main()
