from flockserve import FlockServe
import fire


def start_flockserve(**kwargs):
    fs = FlockServe(**kwargs)
    fs.run()


def main():
    fire.Fire(start_flockserve)


if __name__ == "__main__":
    main()
