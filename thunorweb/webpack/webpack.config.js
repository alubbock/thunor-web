const path = require("path");
const fs = require('fs');
const BundleTracker = require("webpack-bundle-tracker");
const TerserPlugin = require("terser-webpack-plugin");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const CssMinimizerPlugin = require("css-minimizer-webpack-plugin");
const isDebug = (process.env.DJANGO_DEBUG === undefined ? false : process.env.DJANGO_DEBUG.toLowerCase() === "true");
const faviconRoot = './thunor/favicons/'

var config = {
    context: __dirname,

    mode: isDebug ? 'development' : 'production',

    entry: {
        favions: fs.readdirSync(faviconRoot, {withFileTypes: true})
                    .filter(item => !item.isDirectory())
                    .map(item => faviconRoot + item.name),
        app:    ["expose-loader?exposes=pyHTS!./thunor/js/pyhts",
                 "./thunor/css/fonts.css",
                 "./thunor/css/pyhts.css"],

        //TODO: Compile more modules from source, removing unneeded components
        plots:  ["expose-loader?exposes=Plotly!./plotly"],
        sentry: ["expose-loader?exposes=Sentry!./sentry"],
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
                 "bootstrap-fileinput/themes/fa4/theme",
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
        })
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
                type: "asset/resource",
                generator: {filename: 'favicon/[name][ext]'}
            },
            {
                test: /\.(png|jpg|gif|ico)$/,
                exclude: /\/favicons\//,
                type: "asset/resource",
                generator: {filename: 'img/[name]-[hash][ext]'}
            },
            {test: /\.(woff|woff2)(\?v=\d+\.\d+\.\d+)?$/, type: "asset", generator: {filename: "font/[name]-[hash][ext][query]"}},
            {test: /\.ttf(\?v=\d+\.\d+\.\d+)?$/, type: "asset", generator: {filename: "font/[name]-[hash][ext][query]"}},
            {test: /\.eot(\?v=\d+\.\d+\.\d+)?$/, type: "asset/resource", generator: {filename: "font/[name]-[hash][ext][query]"}},
            {test: /\.svg(\?v=\d+\.\d+\.\d+)?$/, type: "asset", generator: {filename: "font/[name]-[hash][ext][query]"}},
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
      minimize: !isDebug,
      minimizer: [
        new TerserPlugin(),
        new CssMinimizerPlugin({})
      ]
    }
};

if (!isDebug) {
    var CompressionPlugin = require("compression-webpack-plugin");
    config.plugins.push(
        new CompressionPlugin({
            test: /\.(js|html|css|ico|map|svg|eot|otf|ttf|json)$/
        })
    );
}

module.exports = config;
