const path = require("path");
const BundleTracker = require("webpack-bundle-tracker");
const UglifyJsPlugin = require("uglifyjs-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const OptimizeCSSAssetsPlugin = require("optimize-css-assets-webpack-plugin");
const glob = require("glob");
const IgnoreUnchangedFilesPlugin = require("ignore-unchanged-webpack-plugin");
const isDebug = (process.env.DJANGO_DEBUG === undefined ? false : process.env.DJANGO_DEBUG.toLowerCase() === "true");

var config = {
    context: __dirname,

    mode: isDebug ? 'development' : 'production',

    entry: {
        favicons: glob.sync("./thunor/favicons/*"),
        app:    ["expose-loader?exposes=pyHTS!./thunor/js/pyhts",
                 "./thunor/css/fonts.css",
                 "./thunor/css/pyhts.css"],

        //TODO: Compile more modules from source, removing unneeded components
        plots:  ["expose-loader?exposes=Plotly!./plotly"],
        sentry: ["expose-loader?exposes=Sentry!@sentry/browser"],
        vendor: ["expose-loader?exposes=jQuery!expose-loader?exposes=$!jquery",      // sitewide
                 // "bootstrap/dist/js/bootstrap",
                 // "bootstrap/dist/css/bootstrap.css",
                 "bootstrap-loader",
                 "font-awesome/css/font-awesome.css",

                 "bootstrap-switch", //toggle switch widget
                 "bootstrap-switch/dist/css/bootstrap3/bootstrap-switch.css",

                 // file downloads
                 "expose-loader?exposes=FileSaver!file-saver",

                // TSV parser
                "d3-dsv",

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
                 "datatables.net-select-bs",
                 "datatables.net-select-bs/css/select.bootstrap.css",
                 "datatables.net-buttons-bs",
                 "datatables.net-buttons-bs/css/buttons.bootstrap.css",
                 "jquery-file-download"]
    },

    output: {
        publicPath: "",
        path: path.resolve("/thunor/_state/webpack-bundles/"),
        filename: "[name]-[chunkhash].js"
    },

    plugins: [
        new BundleTracker({path: "/thunor/_state/webpack-bundles/",
            filename: "webpack-stats.json"}),
        new MiniCssExtractPlugin({
          filename: "[name]-[chunkhash].css",
          chunkFilename: "[id]-[chunkhash].css"
        }),
        new IgnoreUnchangedFilesPlugin()
    ],

    module: {
        rules: [
            {
                test: /\.css$/,
                use: [{
                        loader: MiniCssExtractPlugin.loader
                    },
                    "css-loader"]
            },
            {
                test: /\.(png|ico)$/,
                include: [
                    path.resolve(__dirname, "thunor/favicons"),
                ],
                use: [
                    {
                        loader: 'file-loader',
                        options: {name: 'favicon/[name].[ext]'}
                    }
                ]
            },
            {
                test: /\.(png|jpg|gif|ico)$/,
                exclude: /\/favicons\//,
                use: [
                    {
                        loader: 'file-loader',
                        options: {name: 'img/[name]-[hash].[ext]'}
                    }
                ]
            },
            {test: /\.(woff|woff2)(\?v=\d+\.\d+\.\d+)?$/, loader: "url-loader", options: {limit: 10000, mimetype: "application/font-woff", name: "font/[name]-[hash].[ext]"}},
            {test: /\.ttf(\?v=\d+\.\d+\.\d+)?$/, loader: "url-loader", options: {limit: 10000, mimetype: "application/octet-stream", name: "font/[name]-[hash].[ext]"}},
            {test: /\.eot(\?v=\d+\.\d+\.\d+)?$/, loader: "file-loader", options: {name: "font/[name]-[hash].[ext]"}},
            {test: /\.svg(\?v=\d+\.\d+\.\d+)?$/, loader: "url-loader", options: {limit: 10000, mimetype: "image/svg+xml&name=font/[name]-[hash].[ext]"}},
            // Load existing source maps, if desired (disabled by default)
            //{test:  /\.js$/, use: ["source-map-loader"], enforce: "pre"}
        ]
    },
    devtool: 'source-map',

    resolve: {
        modules: ["node_modules"],
        extensions: [".js"],
        alias: {
            "jquery-ui-js": "jquery-ui/ui",
            "jquery-ui-css": "jquery-ui/themes/base"
        }
    },

    optimization: {
      minimizer: [
        new UglifyJsPlugin({
          cache: true,
          parallel: true,
          sourceMap: true // set to true if you want JS source maps
        }),
        new OptimizeCSSAssetsPlugin({})
      ]
    }
};

if (!isDebug) {
    var CompressionPlugin = require("compression-webpack-plugin");
    config.plugins.push(
        new CompressionPlugin({
            test: /\.(js|html|css|ico|map|svg|eot|otf|ttf|json)$/,
            cache: true
        })
    );
}

module.exports = config;
