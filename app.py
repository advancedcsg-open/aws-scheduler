from flask import Flask, request
app = Flask(__name__)

@app.route("/api/schedule", methods=['POST'])
def scheduleTask():
    return "Hello World! from POST"

@app.route("/api/schedule", methods=['GET'])
def getTask():
    args = request.args
    print(args)
    app = ""
    id = ""
    if "application" in args:
        app = args["application"]
    if "eventIdentifier" in args:
        id = args.get("eventIdentifier")
    return "Hello World! from GET " + app + " " + id

@app.route("/api/schedule/<app>/<id>", methods=['PUT'])
def updateTask(app, id):
    args = request.view_args['app']
    print(args)
    return "Hello World! from PUT" + app + " " + id

@app.route("/api/schedule/<app>/<id>", methods=['DELETE'])
def deleteTask(app, id):
    args = request.view_args['app']
    print(args)
    return "Hello World! from delete " + app + " " + id


