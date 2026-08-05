from app.vector_store import build_vector_index


def main() -> None:
    build_vector_index()
    print("Vector index built successfully.")


if __name__ == "__main__":
    main()