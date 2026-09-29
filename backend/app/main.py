"""Flask 应用入口 — python -m app.main 或 flask --app app.main run"""
import logging

from flask import Flask, jsonify


def create_app() -> Flask:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    from app.api.routes import bp

    app.register_blueprint(bp)

    @app.after_request
    def add_cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "not found"}), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
