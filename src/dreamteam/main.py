
def main():
    """Run the Fahrplan-Diskrepanz-Analyzer Flask app."""
    from .app import app
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    main()
