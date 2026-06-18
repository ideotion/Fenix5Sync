# Vendored third-party assets

These files are committed to the repository so the GUI works fully offline with
no runtime CDN or build step. They are not authored here; their original
licenses apply.

| File            | Library  | Version | License | Source                                   |
|-----------------|----------|---------|---------|------------------------------------------|
| `chart.umd.js`  | Chart.js | 4.4.1   | MIT     | https://www.chartjs.org / npm `chart.js` |

To refresh Chart.js (requires network at build time only):

```sh
curl -fsSL https://registry.npmjs.org/chart.js/-/chart.js-4.4.1.tgz -o /tmp/chart.tgz
tar -xzf /tmp/chart.tgz -C /tmp
cp /tmp/package/dist/chart.umd.js web/vendor/chart.umd.js
```
