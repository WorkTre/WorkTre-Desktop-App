/****************************************************************************
**
** qwebchannel.js - Minimal version
**
****************************************************************************/

(function () {
    if (window.QWebChannel) {
        return;
    }

    var QWebChannel = function (transport, initCallback) {
        var channel = this;
        this.transport = transport;

        this.send = function (data) {
            transport.send(JSON.stringify(data));
        };

        this.transport.onmessage = function (message) {
            var data = JSON.parse(message.data);
            if (data.type === "signal") {
                var object = channel.objects[data.object];
                if (object) {
                    var signal = object[data.signal];
                    if (signal) {
                        signal.apply(object, data.args);
                    }
                }
            } else if (data.type === "response") {
                var callback = channel.callbacks[data.id];
                if (callback) {
                    callback(data.data);
                    delete channel.callbacks[data.id];
                }
            }
        };

        this.objects = {};
        this.callbacks = {};
        this.nextCallbackId = 0;

        this.exec = function (object, method, args, callback) {
            var id = this.nextCallbackId++;
            if (callback) {
                this.callbacks[id] = callback;
            }
            this.send({
                type: "invokeMethod",
                object: object.__id__,
                method: method,
                args: args,
                id: id
            });
        };

        this.send({type: "init"});
        this.transport.onmessage({data: JSON.stringify({type: "initDone", objects: {api: {__id__: "api"}}})});
        this.objects.api = {
            __id__: "api",
            inactivity: function (eid, status) {
                return new Promise((resolve) => {
                    channel.exec(this, "inactivity", [eid, status], resolve);
                });
            }
        };

        if (initCallback) {
            initCallback(this);
        }
    };

    window.QWebChannel = QWebChannel;
})();
