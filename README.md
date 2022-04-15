# Convex Strategy Template

## Getting started

- If you're unfamiliar with yearn vaults or strategies, check out our [explainer](https://medium.com/iearn/yearn-finance-explained-what-are-vaults-and-strategies-96970560432), [docs](https://docs.yearn.finance/getting-started/products/yvaults/overview), the [vaults repo](https://github.com/yearn/yearn-vaults), or our [brownie strategy mix](https://github.com/yearn/brownie-strategy-mix).

- This repo contains multiple iterations of Yearn's strategy for Convex Finance. These strategies deposit Curve LP tokens, harvest CRV, CVX, and other token yield, and compound the gains into more of the underlying Curve LP.

- The `main` branch features the most current implementation for 3crv factory pools. Check out other branches to see slight tweaks made for different pools. If you have any questions, feel free to reach out.
