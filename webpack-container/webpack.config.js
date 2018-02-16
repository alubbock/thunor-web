var path = require("path");
var webpack = require("webpack");
var BundleTracker = require("webpack-bundle-tracker");
var ExtractTextPlugin = require("extract-text-webpack-plugin");
var glob = require("glob");
var isDebug = (process.env.DJANGO_DEBUG === undefined ? false : process.env.DJANGO_DEBUG.toLowerCase() === "true");

var config = {
    context: __dirname,

    entry: {
        favicons: glob.sync("./thunor/favicons/*"),
        app:    ["expose-loader?pyHTS!./thunor/js/pyhts",
                 "./thunor/css/fonts.css",
                 "./thunor/css/pyhts.css"],

        //TODO: Compile more modules from source, removing unneeded components
        plots:  ["expose-loader?Plotly!./plotly"],
        raven:  ["expose-loader?Raven!raven-js"],
        vendor: ["expose-loader?jQuery!expose-loader?$!jquery",      // sitewide
                 // "bootstrap/dist/js/bootstrap",
                 // "bootstrap/dist/css/bootstrap.css",
                 "bootstrap-loader",
                 "font-awesome/css/font-awesome.css",

                 "bootstrap-switch", //toggle switch widget
                 "bootstrap-switch/dist/css/bootstrap3/bootstrap-switch.css",

                 // file downloads
                 "expose-loader?FileSaver!file-saver",

                 "bootstrap-fileinput",//uploader
                 "bootstrap-fileinput/themes/fa/theme",
                 "bootstrap-fileinput/css/fileinput.css",//uploader
                 "bootstrap-select",//plate mapper
                 "bootstrap-select/dist/css/bootstrap-select.css",//plate map
                 "typeahead.js/dist/typeahead.jquery",//plate mapper
                 "jquery-ui-js/widgets/sortable",//plots interface
                 "jquery-ui-js/widgets/selectable",//plate mapper
                 "jquery-ui-css/core.css",
                 "jquery-ui-css/selectable.css",
                 "jquery-ui-css/sortable.css",
                 "jquery-ui-css/theme.css",
                 "jquery-ui-touch-punch",
                 "datatables.net",
                 "datatables.net-bs",
                 "datatables.net-bs/css/dataTables.bootstrap.css",
                 "jquery-file-download"]
    },

    output: {
        path: path.resolve("../_state/webpack-bundles/"),
        filename: "[name]-[chunkhash].js"
    },

    plugins: [
        new BundleTracker({path: __dirname,
            filename: "../_state/webpack-bundles/webpack-stats.json"}),
        new ExtractTextPlugin("[name]-[chunkhash].css")
    ],

    module: {
        rules: [
            {
                // required by plotly
                test: /node_modules/,
                include: [/node_modules\/(plotly|glsl-|gl-|cwise)/],
                loader: "ify-loader"
            },
            {
                test: /\.css$/,
                loader: ExtractTextPlugin.extract({
                    loader: "css-loader",
                    options: {minimize: !isDebug}
                })
            },
            {
                test: /\.(png|ico)$/,
                include: [
                    path.resolve(__dirname, "thunor/favicons"),
                    path.resolve(__dirname, "../thunorweb/static/thunorweb/favicons")
                ],
                loader: "file-loader?name=favicon/[name].[ext]"
            },
            {
                test: /\.(png|jpg|gif|ico)$/,
                exclude: /\/favicons\//,
                loader: "file-loader?name=img/[name]-[hash].[ext]"
            },
            {test: /\.(woff|woff2)(\?v=\d+\.\d+\.\d+)?$/, loader: "url-loader?limit=10000&mimetype=application/font-woff&name=font/[name]-[hash].[ext]"},
            {test: /\.ttf(\?v=\d+\.\d+\.\d+)?$/, loader: "url-loader?limit=10000&mimetype=application/octet-stream&name=font/[name]-[hash].[ext]"},
            {test: /\.eot(\?v=\d+\.\d+\.\d+)?$/, loader: "file-loader?name=font/[name]-[hash].[ext]"},
            {test: /\.svg(\?v=\d+\.\d+\.\d+)?$/, loader: "url-loader?limit=10000&mimetype=image/svg+xml&name=font/[name]-[hash].[ext]"}
        ]
    },

    resolve: {
        modules: ["node_modules"],
        extensions: [".js"],
        alias: {
            "jquery-ui-js": "jquery-ui/ui",
            "jquery-ui-css": "jquery-ui/themes/base"
        }
    }
};

if (!isDebug) {
    config.plugins.push(
        new webpack.optimize.UglifyJsPlugin({
            compress: {
                screw_ie8: true,
                warnings: false
            },
            mangle: true
        })
    );
    config.plugins.push(
        new webpack.SourceMapDevToolPlugin({
            filename: "[file].map",
            include: /^app/
        })
    );
    var CompressionPlugin = require("compression-webpack-plugin");
    config.plugins.push(
        new CompressionPlugin({
            test: /\.(js|html|css|ico|map|svg|eot|otf|ttf|json)$/
        })
    );
}

module.exports = config;
