// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

// These are the core Yearn libraries
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/math/SafeMath.sol";
import "@openzeppelin/contracts/utils/Address.sol";
import "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";
import "@openzeppelin/contracts/math/Math.sol";

import "./interfaces/curve.sol";
import {IUniswapV2Router02} from "./interfaces/uniswap.sol";
// these are the libraries to use with synthetix
import "./interfaces/synthetix.sol";

interface IUniV3 {
    struct ExactInputParams {
        bytes path;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
    }

    function exactInput(ExactInputParams calldata params)
        external
        payable
        returns (uint256 amountOut);
}

interface IVault is IERC20 {
    // NOTE: Vyper produces multiple signatures for a given function with "default" args
    function deposit() external returns (uint256);

    function deposit(uint256 amount) external returns (uint256);

    function deposit(uint256 amount, address recipient)
        external
        returns (uint256);

    function withdraw() external returns (uint256);

    function token() external view returns (address);
}

interface IWeth {
    function deposit() external payable;

    function withdraw(uint256 wad) external;
}

contract FixedForexZap {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;

    /* ========== STATE VARIABLES ========== */

    IReadProxy internal constant readProxy =
        IReadProxy(0x4E3b31eB0E5CB73641EE1E65E7dCEFe520bA3ef2);
    ISystemStatus internal constant systemStatus =
        ISystemStatus(0x1c86B3CDF2a60Ae3a574f7f71d44E2C50BDdB87E); // this is how we check if our market is closed

    bytes32 internal constant TRACKING_CODE = "YEARN"; // this is our referral code for SNX volume incentives
    bytes32 internal constant CONTRACT_SYNTHETIX = "Synthetix";
    bytes32 internal constant CONTRACT_EXCHANGER = "Exchanger";

    address internal constant uniswapv3 =
        0xE592427A0AEce92De3Edee1F18E0157C05861564;

    /* ========== CONSTRUCTOR ========== */

    constructor() public {
        // approve the uniV3 router to spend our zap tokens and our sETH (for zapping out)
        IERC20 weth = IERC20(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
        IERC20 wbtc = IERC20(0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599);
        IERC20 dai = IERC20(0x6B175474E89094C44Da98b954EedeAC495271d0F);
        IERC20 usdc = IERC20(0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48);
        IERC20 usdt = IERC20(0xdAC17F958D2ee523a2206206994597C13D831ec7);
        IERC20 seth = IERC20(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb);

        weth.approve(uniswapv3, type(uint256).max);
        usdc.approve(uniswapv3, type(uint256).max);
        dai.approve(uniswapv3, type(uint256).max);
        usdt.safeApprove(uniswapv3, type(uint256).max);
        wbtc.approve(uniswapv3, type(uint256).max);
        seth.approve(uniswapv3, type(uint256).max);

        // approve our curve LPs to spend our synths
        IERC20 aud = IERC20(0xF48e200EAF9906362BB1442fca31e0835773b8B4);
        IERC20 chf = IERC20(0x0F83287FF768D1c1e17a42F44d644D7F22e8ee1d);
        IERC20 eur = IERC20(0xD71eCFF9342A5Ced620049e616c5035F1dB98620);
        IERC20 gbp = IERC20(0x97fe22E7341a0Cd8Db6F6C021A24Dc8f4DAD855F);
        IERC20 jpy = IERC20(0xF6b1C627e95BFc3c1b4c9B825a032Ff0fBf3e07d);
        IERC20 krw = IERC20(0x269895a3dF4D73b077Fc823dD6dA1B95f72Aaf9B);

        aud.approve(
            address(0x3F1B0278A9ee595635B61817630cC19DE792f506),
            type(uint256).max
        );
        chf.approve(
            address(0x9c2C8910F113181783c249d8F6Aa41b51Cde0f0c),
            type(uint256).max
        );
        eur.approve(
            address(0x19b080FE1ffA0553469D20Ca36219F17Fcf03859),
            type(uint256).max
        );
        gbp.approve(
            address(0xD6Ac1CB9019137a896343Da59dDE6d097F710538),
            type(uint256).max
        );
        jpy.approve(
            address(0x8818a9bb44Fbf33502bE7c15c500d0C783B73067),
            type(uint256).max
        );
        krw.approve(
            address(0x8461A004b50d321CB22B7d034969cE6803911899),
            type(uint256).max
        );

        // approve our vaults to spend our curve LPs
        aud = IERC20(0x3F1B0278A9ee595635B61817630cC19DE792f506);
        chf = IERC20(0x9c2C8910F113181783c249d8F6Aa41b51Cde0f0c);
        eur = IERC20(0x19b080FE1ffA0553469D20Ca36219F17Fcf03859);
        gbp = IERC20(0xD6Ac1CB9019137a896343Da59dDE6d097F710538);
        jpy = IERC20(0x8818a9bb44Fbf33502bE7c15c500d0C783B73067);
        krw = IERC20(0x8461A004b50d321CB22B7d034969cE6803911899);

        aud.approve(
            address(0x1b905331F7dE2748F4D6a0678e1521E20347643F),
            type(uint256).max
        );
        chf.approve(
            address(0x490bD0886F221A5F79713D3E84404355A9293C50),
            type(uint256).max
        );
        eur.approve(
            address(0x67e019bfbd5a67207755D04467D6A70c0B75bF60),
            type(uint256).max
        );
        gbp.approve(
            address(0x595a68a8c9D5C230001848B69b1947ee2A607164),
            type(uint256).max
        );
        jpy.approve(
            address(0x59518884EeBFb03e90a18ADBAAAB770d4666471e),
            type(uint256).max
        );
        krw.approve(
            address(0x528D50dC9a333f01544177a924893FA1F5b9F748),
            type(uint256).max
        );
    }

    /* ========== ZAP IN ========== */

    // zap in for sETH
    function zapIn(
        address _inputToken,
        uint256 _amount,
        address _vaultToken
    ) public payable {
        require(_amount > 0 || msg.value > 0); // dev: invalid token or ETH amount

        if (_inputToken == 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE) {
            // if we start with ETH
            //convert ETH to WETH
            IWeth weth = IWeth(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
            _amount = msg.value;
            weth.deposit{value: _amount}();

            // swap for sETH
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2), // weth
                        uint24(500),
                        address(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb) // sETH
                    ),
                    address(this),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );
        } else if (
            // this is if we start with WETH
            _inputToken == address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2)
        ) {
            //transfer token
            IERC20(_inputToken).safeTransferFrom(
                msg.sender,
                address(this),
                _amount
            );

            // swap for sETH
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(_inputToken),
                        uint24(500),
                        address(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb) // sETH
                    ),
                    address(this),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );
        } else if (
            // this is DAI, 0.3% is much better liquidity sadly
            _inputToken == address(0x6B175474E89094C44Da98b954EedeAC495271d0F)
        ) {
            //transfer token
            IERC20(_inputToken).safeTransferFrom(
                msg.sender,
                address(this),
                _amount
            );

            // swap for sETH
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(_inputToken),
                        uint24(3000),
                        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2), // weth
                        uint24(500),
                        address(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb) // sETH
                    ),
                    address(this),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );
        } else {
            //transfer token
            IERC20(_inputToken).safeTransferFrom(
                msg.sender,
                address(this),
                _amount
            );

            // this is if we start with any token but WETH or DAI
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(_inputToken),
                        uint24(500),
                        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2), // weth
                        uint24(500),
                        address(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb) // sETH
                    ),
                    address(this),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );
        }
        // check our output balance of sETH
        IERC20 seth = IERC20(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb);
        uint256 _sEthBalance = seth.balanceOf(address(this));

        // generate our synth currency key to check if enough time has elapsed
        address _synth;
        bytes32 _synthCurrencyKey;
        if (_vaultToken == 0x1b905331F7dE2748F4D6a0678e1521E20347643F) {
            // sAUD
            _synth = 0xF48e200EAF9906362BB1442fca31e0835773b8B4;
            _synthCurrencyKey = "sAUD";
        } else if (_vaultToken == 0x490bD0886F221A5F79713D3E84404355A9293C50) {
            // sCHF
            _synth = 0x0F83287FF768D1c1e17a42F44d644D7F22e8ee1d;
            _synthCurrencyKey = "sCHF";
        } else if (_vaultToken == 0x67e019bfbd5a67207755D04467D6A70c0B75bF60) {
            // sEUR
            _synth = 0xD71eCFF9342A5Ced620049e616c5035F1dB98620;
            _synthCurrencyKey = "sEUR";
        } else if (_vaultToken == 0x595a68a8c9D5C230001848B69b1947ee2A607164) {
            // sGBP
            _synth = 0x97fe22E7341a0Cd8Db6F6C021A24Dc8f4DAD855F;
            _synthCurrencyKey = "sGBP";
        } else if (_vaultToken == 0x59518884EeBFb03e90a18ADBAAAB770d4666471e) {
            // sJPY
            _synth = 0xF6b1C627e95BFc3c1b4c9B825a032Ff0fBf3e07d;
            _synthCurrencyKey = "sJPY";
        } else if (_vaultToken == 0x528D50dC9a333f01544177a924893FA1F5b9F748) {
            // sKRW
            _synth = 0x269895a3dF4D73b077Fc823dD6dA1B95f72Aaf9B;
            _synthCurrencyKey = "sKRW";
        } else {
            require(false); // dev: not a Fixed Forex vault token
        }

        // check if our forex markets are open
        require(!isMarketClosed(_synth)); // dev: synthetix forex markets currently closed

        // swap our sETH for our underlying synth
        exchangeSEthToSynth(_sEthBalance, _synthCurrencyKey);
    }

    function exchangeSEthToSynth(uint256 _amount, bytes32 _synthCurrencyKey)
        internal
    {
        // swap amount of sETH for Synth
        require(_amount > 0); // dev: invalid token or ETH amount

        bytes32 _sethCurrencyKey = "sETH";

        _synthetix().exchangeWithTrackingForInitiator(
            _sethCurrencyKey,
            _amount,
            _synthCurrencyKey,
            address(0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7),
            TRACKING_CODE
        );
    }

    function synthToVault(address _synth, uint256 _amount) external {
        require(_amount > 0); // dev: invalid token or ETH amount
        // make sure the user has the synth needed
        address _user = msg.sender;
        IERC20 synth = IERC20(_synth);
        uint256 _synthBalance = synth.balanceOf(_user);
        require(_synthBalance > 0); // dev: you don't hold any of the specified synth
        synth.transferFrom(_user, address(this), _amount);

        // generate our synth currency key first to check if enough time has elapsed
        bytes32 _synthCurrencyKey;
        if (_synth == 0xF48e200EAF9906362BB1442fca31e0835773b8B4) {
            // sAUD
            _synthCurrencyKey = "sAUD";
        } else if (_synth == 0x0F83287FF768D1c1e17a42F44d644D7F22e8ee1d) {
            // sCHF
            _synthCurrencyKey = "sCHF";
        } else if (_synth == 0xD71eCFF9342A5Ced620049e616c5035F1dB98620) {
            // sEUR
            _synthCurrencyKey = "sEUR";
        } else if (_synth == 0x97fe22E7341a0Cd8Db6F6C021A24Dc8f4DAD855F) {
            // sGBP
            _synthCurrencyKey = "sGBP";
        } else if (_synth == 0xF6b1C627e95BFc3c1b4c9B825a032Ff0fBf3e07d) {
            // sJPY
            _synthCurrencyKey = "sJPY";
        } else if (_synth == 0x269895a3dF4D73b077Fc823dD6dA1B95f72Aaf9B) {
            // sKRW
            _synthCurrencyKey = "sKRW";
        } else {
            require(false); // dev: not a Fixed Forex synth
        }

        // deposit our sToken to Curve but only if our trade has finalized
        require(checkWaitingPeriod(msg.sender, _synthCurrencyKey)); // dev: wait ~6mins for trade to finalize on synthetix

        if (_synth == 0xF48e200EAF9906362BB1442fca31e0835773b8B4) {
            // sAUD
            ICurveFi curve =
                ICurveFi(0x3F1B0278A9ee595635B61817630cC19DE792f506); // Curve LP/Pool
            curve.add_liquidity([0, _amount], 0);
            uint256 _poolBalance = curve.balanceOf(address(this));
            IVault(0x1b905331F7dE2748F4D6a0678e1521E20347643F).deposit(
                _poolBalance,
                _user
            );
        } else if (_synth == 0x0F83287FF768D1c1e17a42F44d644D7F22e8ee1d) {
            // sCHF
            ICurveFi curve =
                ICurveFi(0x9c2C8910F113181783c249d8F6Aa41b51Cde0f0c); // Curve LP/Pool
            curve.add_liquidity([0, _amount], 0);
            uint256 _poolBalance = curve.balanceOf(address(this));
            IVault(0x490bD0886F221A5F79713D3E84404355A9293C50).deposit(
                _poolBalance,
                _user
            );
        } else if (_synth == 0xD71eCFF9342A5Ced620049e616c5035F1dB98620) {
            // sEUR
            ICurveFi curve =
                ICurveFi(0x19b080FE1ffA0553469D20Ca36219F17Fcf03859); // Curve LP/Pool
            curve.add_liquidity([0, _amount], 0);
            uint256 _poolBalance = curve.balanceOf(address(this));
            IVault(0x67e019bfbd5a67207755D04467D6A70c0B75bF60).deposit(
                _poolBalance,
                _user
            );
        } else if (_synth == 0x97fe22E7341a0Cd8Db6F6C021A24Dc8f4DAD855F) {
            // sGBP
            ICurveFi curve =
                ICurveFi(0xD6Ac1CB9019137a896343Da59dDE6d097F710538); // Curve LP/Pool
            curve.add_liquidity([0, _amount], 0);
            uint256 _poolBalance = curve.balanceOf(address(this));
            IVault(0x595a68a8c9D5C230001848B69b1947ee2A607164).deposit(
                _poolBalance,
                _user
            );
        } else if (_synth == 0xF6b1C627e95BFc3c1b4c9B825a032Ff0fBf3e07d) {
            // sJPY
            ICurveFi curve =
                ICurveFi(0x8818a9bb44Fbf33502bE7c15c500d0C783B73067); // Curve LP/Pool
            curve.add_liquidity([0, _amount], 0);
            uint256 _poolBalance = curve.balanceOf(address(this));
            IVault(0x59518884EeBFb03e90a18ADBAAAB770d4666471e).deposit(
                _poolBalance,
                _user
            );
        } else {
            // sKRW
            ICurveFi curve =
                ICurveFi(0x8461A004b50d321CB22B7d034969cE6803911899); // Curve LP/Pool
            curve.add_liquidity([0, _amount], 0);
            uint256 _poolBalance = curve.balanceOf(address(this));
            IVault(0x528D50dC9a333f01544177a924893FA1F5b9F748).deposit(
                _poolBalance,
                _user
            );
        }
    }

    /* ========== ZAP OUT ========== */

    // zap our tokens for sETH
    function zapOut(address _vaultToken, uint256 _amount) external {
        require(_amount > 0); // dev: invalid token or ETH amount
        address _user = msg.sender;

        // withdraw from our vault
        IVault _vault = IVault(_vaultToken);
        _vault.transferFrom(_user, address(this), _amount);
        _vault.withdraw();

        // withdraw from our Curve pool
        ICurveFi curve = ICurveFi(_vault.token()); // our curve pool is the underlying token for our vault
        uint256 _poolBalance = curve.balanceOf(address(this));
        curve.remove_liquidity_one_coin(_poolBalance, 1, 0);

        // check our output balance of synth
        address _synth = curve.coins(1); // our synth is the second token in each of the curve pools
        IERC20 synth = IERC20(_synth);
        uint256 _synthBalance = synth.balanceOf(address(this));

        // generate our synth currency key to check if enough time has elapsed
        bytes32 _synthCurrencyKey;
        if (_vaultToken == 0x1b905331F7dE2748F4D6a0678e1521E20347643F) {
            // sAUD
            _synthCurrencyKey = "sAUD";
        } else if (_vaultToken == 0x490bD0886F221A5F79713D3E84404355A9293C50) {
            // sCHF
            _synthCurrencyKey = "sCHF";
        } else if (_vaultToken == 0x67e019bfbd5a67207755D04467D6A70c0B75bF60) {
            // sEUR
            _synthCurrencyKey = "sEUR";
        } else if (_vaultToken == 0x595a68a8c9D5C230001848B69b1947ee2A607164) {
            // sGBP
            _synthCurrencyKey = "sGBP";
        } else if (_vaultToken == 0x59518884EeBFb03e90a18ADBAAAB770d4666471e) {
            // sJPY
            _synthCurrencyKey = "sJPY";
        } else if (_vaultToken == 0x528D50dC9a333f01544177a924893FA1F5b9F748) {
            // sKRW
            _synthCurrencyKey = "sKRW";
        } else {
            require(false); // dev: not a Fixed Forex vault token
        }

        // check if our forex markets are open
        require(!isMarketClosed(_synth)); // dev: synthetix forex markets currently closed

        // swap our sETH for our underlying synth
        exchangeSynthToSEth(_synthBalance, _synthCurrencyKey);
    }

    function exchangeSynthToSEth(uint256 _amount, bytes32 _synthCurrencyKey)
        internal
    {
        // swap amount of sETH for Synth
        require(_amount > 0); // dev: can't swap zero

        bytes32 _sethCurrencyKey = "sETH";

        _synthetix().exchangeWithTrackingForInitiator(
            _synthCurrencyKey,
            _amount,
            _sethCurrencyKey,
            address(0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7),
            TRACKING_CODE
        );
    }

    function sETHToWant(address _targetToken, uint256 _amount) external {
        // make sure that our synth trade has finalized
        bytes32 _sethCurrencyKey = "sETH";
        require(checkWaitingPeriod(msg.sender, _sethCurrencyKey)); // dev: wait ~6mins for trade to finalize on synthetix
        require(_amount > 0); // dev: invalid token or ETH amount

        //transfer sETH to zap
        address payable _user = msg.sender;
        IERC20 seth = IERC20(0x5e74C9036fb86BD7eCdcb084a0673EFc32eA31cb);
        uint256 _sethBalance = seth.balanceOf(_user);
        require(_sethBalance > 0); // dev: you don't hold any sETH
        seth.safeTransferFrom(_user, address(this), _amount);

        // this is if we want to end up with WETH
        if (
            _targetToken == address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2)
        ) {
            // swap for sETH
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(seth),
                        uint24(500),
                        address(_targetToken)
                    ),
                    address(_user),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );
        } else if (
            _targetToken == address(0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE)
        ) {
            // swap for WETH
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(seth),
                        uint24(500),
                        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2) // weth
                    ),
                    address(this),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );

            //convert WETH to ETH
            address weth = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
            uint256 _output = IERC20(weth).balanceOf(address(this));
            if (_output > 0) {
                IWeth(weth).withdraw(_output);
                _user.transfer(_output);
            }
        } else if (
            // for DAI it's best to use 0.3% fee route
            _targetToken == address(0x6B175474E89094C44Da98b954EedeAC495271d0F)
        ) {
            // swap for DAI
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(seth),
                        uint24(500),
                        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2),
                        uint24(3000),
                        address(_targetToken)
                    ),
                    address(_user),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );
        } else {
            // this is if we want any token but WETH or DAI
            IUniV3(uniswapv3).exactInput(
                IUniV3.ExactInputParams(
                    abi.encodePacked(
                        address(seth),
                        uint24(500),
                        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2),
                        uint24(500),
                        address(_targetToken)
                    ),
                    address(_user),
                    block.timestamp,
                    _amount,
                    uint256(1)
                )
            );
        }
    }

    // include so our zap plays nicely with ether
    receive() external payable {}

    /* ========== HELPERS ========== */

    function _synthetix() internal view returns (ISynthetix) {
        return ISynthetix(resolver().getAddress(CONTRACT_SYNTHETIX));
    }

    function resolver() internal view returns (IAddressResolver) {
        return IAddressResolver(readProxy.target());
    }

    function _exchanger() internal view returns (IExchanger) {
        return IExchanger(resolver().getAddress(CONTRACT_EXCHANGER));
    }

    function checkWaitingPeriod(address _user, bytes32 _synthCurrencyKey)
        internal
        view
        returns (bool freeToMove)
    {
        return
            // check if it's been >5 mins since we traded our sETH for our synth
            _exchanger().maxSecsLeftInWaitingPeriod(
                address(_user),
                _synthCurrencyKey
            ) == 0;
    }

    function isMarketClosed(address _synth) public view returns (bool) {
        // keep this public so we can always check if markets are open
        bytes32 _synthCurrencyKey;
        if (_synth == 0xF48e200EAF9906362BB1442fca31e0835773b8B4) {
            // sAUD
            _synthCurrencyKey = "sAUD";
        } else if (_synth == 0x0F83287FF768D1c1e17a42F44d644D7F22e8ee1d) {
            // sCHF
            _synthCurrencyKey = "sCHF";
        } else if (_synth == 0xD71eCFF9342A5Ced620049e616c5035F1dB98620) {
            // sEUR
            _synthCurrencyKey = "sEUR";
        } else if (_synth == 0x97fe22E7341a0Cd8Db6F6C021A24Dc8f4DAD855F) {
            // sGBP
            _synthCurrencyKey = "sGBP";
        } else if (_synth == 0xF6b1C627e95BFc3c1b4c9B825a032Ff0fBf3e07d) {
            // sJPY
            _synthCurrencyKey = "sJPY";
        } else {
            // sKRW
            _synthCurrencyKey = "sKRW";
        }

        // set up our arrays to use
        bool[] memory tradingSuspended;
        bytes32[] memory synthArray;

        // use our synth key
        synthArray = new bytes32[](1);
        synthArray[0] = _synthCurrencyKey;

        // check if trading is open or not. true = market is closed
        (tradingSuspended, ) = systemStatus.getSynthExchangeSuspensions(
            synthArray
        );
        return tradingSuspended[0];
    }
}
