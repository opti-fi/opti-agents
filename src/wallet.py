import os
import orjson
from cdp import Cdp, Wallet, WalletData
from src.utils import get_env_variable

class AgentWallet:
    def __init__(self):
        self.api_key = get_env_variable("CDP_API_KEY_NAME")
        self.private_key = get_env_variable("CDP_API_KEY_PRIVATE_KEY")
        self.file_path = "./data/wallet.json"
        Cdp.configure(self.api_key, self.private_key)

    async def create_wallet(self, user_address):
        existing_data = await self._load_existing_data()
        
        for entry in existing_data:
            if entry["user_address"] == user_address:
                print(f"Wallet already exists for user address: {user_address}")
                return
        
        wallet = Wallet.create(network_id="base-sepolia")
        wallet_data = wallet.export_data()
        await self.save_wallet_data(wallet_data, user_address)
        

    async def save_wallet_data(self, wallet_data, user_address):
        wallet_data_dict = wallet_data.to_dict()
        output_data = {
            "user_address": user_address,
            "data": wallet_data_dict
        }

        existing_data = await self._load_existing_data()
        existing_data.append(output_data)
        await self._save_data(existing_data)
        print("Wallet data saved successfully.")

    async def fetch_data(self, user_address):
        existing_data = await self._load_existing_data()

        for entry in existing_data:
            if entry["user_address"] == user_address:
                wallet_data_dict = entry["data"]
                wallet_data = WalletData.from_dict(wallet_data_dict)
                wallet = Wallet.import_wallet(wallet_data)
                
                return wallet

        print(f"No wallet data found for user address: {user_address}")
        return None
    
    async def _check_address(self, user_address):
        wallet = await self.fetch_data(user_address)
        address = wallet.default_address
        return address.address_id
    
    # Fund wallet via mpc
    async def _fund_wallet(self, user_address):
        wallet = await self.fetch_data(user_address)
        faucet = wallet.faucet(asset_id='eth')
        faucet.wait()
        return faucet.transaction_hash
    
    async def _transfer(self, user_address, amount, asset_id, destination):
        wallet = await self.fetch_data(user_address)
        transaction = wallet.transfer(amount, asset_id, destination)
        transaction.wait()
        return transaction.transaction_hash
    
    async def _get_token_ca(self, asset_id):
        match asset_id:
            case "usdc":
                return "0x0E8Ac3cc5183A243FcbA007136135A14831fDA99"
            case "uni":
                return "0x1eaC9BB63f8673906dBb75874356E33Ab7d5D780"
            case "weth":
                return "0xD1d25fc5faC3cd5EE2daFE6292C5DFC16057D4d1"
            case "usdt":
                return "0xbF1876d7643a1d7DA52C7B8a67e7D86aeeAA12A6"
            case "dai":
                return "0x134C06B12eA6b1c7419a08085E0de6bDA9A16dA2"
    
    async def _get_protocol_ca(self, protocol):
        match protocol:
            case "uniswap":
                return "0xa42A86906D3FDfFE7ccc1a4E143e5Ddd8dF0Cf83"
            case "compoundv3":
                return "0xD1b1954896009800dF01b197A6E8E1d98FF44ae8"
            case "usdxmoney":
                return "0x6c36eD76d3FF0A7C0309aef473052b487895Fadf"
            case "stargatev3":
                return "0x0CAf83Ef2BA9242F174FCE98E30B9ceba299aaa3"
            case "aavev3":
                return "0x5dC10711C60dd5174306aEC6Fb1c78b895C9fA5A"
    
    async def mint(self, user_address, asset_id, amount):
        amount = int(amount) * (10 ** 6)
        abi = await self._read_abi("./abi/MockToken.json")
        
        wallet = await self.fetch_data(user_address)
        address = wallet.default_address.address_id
        
        invocation = wallet.invoke_contract(
            contract_address=await self._get_token_ca(asset_id),
            abi=abi,
            method="mint",
            args={"to": address, "amount": str(int(amount))}
        )

        invocation.wait()
        
        return invocation.transaction_hash
    
    async def transfer(self, user_address, contract_address, to, amount):
        amount = int(amount) * (10 ** 6)
        abi = await self._read_abi("./abi/MockToken.json")
        
        wallet = await self.fetch_data(user_address)
        
        invocation = wallet.invoke_contract(
            contract_address=contract_address,
            abi=abi,
            method="transfer",
            args={"to": str(to), "value": str(int(amount))}
        )

        invocation.wait()
        
        return invocation.transaction_hash
    
    async def swap(self, user_address, spender, token_in, token_out, amount):
        approve_abi = await self._read_abi("./abi/MockToken.json")
        amount = int(amount) * (10 ** 6)
        
        wallet = await self.fetch_data(user_address)
        approve_incovation = wallet.invoke_contract(
            contract_address=token_in,
            abi=approve_abi,
            method="approve",
            args={"spender": spender, "amount": str(int(amount + 10))}
        )
        approve_incovation.wait()
        
        abi = await self._read_abi("./abi/OptiFinance.json")
        
        invocation = wallet.invoke_contract(
            contract_address="0x9F7b08e2365BFf594C4227752741Cb696B9b6E71",
            abi=abi,
            method="swap",
            args={"tokenIn": token_in, "tokenOut": token_out, "amountIn": str(int(amount))}
        )

        invocation.wait()
        
        return invocation.transaction_hash
    
    async def stake(self, user_address, asset_id, protocol, spender, amount):
        approve_abi = await self._read_abi("./abi/MockToken.json")
        amount = int(amount) * (10 ** 6)
        
        wallet = await self.fetch_data(user_address)
        approve_incovation = wallet.invoke_contract(
            contract_address=await self._get_token_ca(asset_id),
            abi=approve_abi,
            method="approve",
            args={"spender": spender, "amount": str(int(amount + 10))}
        )
        approve_incovation.wait()
        
        abi = await self._read_abi("./abi/MockStake.json")
        
        invocation = wallet.invoke_contract(
            contract_address=await self._get_protocol_ca(protocol),
            abi=abi,
            method="stake",
            args={"_days": str(0), "_amount": str(int(amount))}
        )

        invocation.wait()
        
        return invocation.transaction_hash
    
    
    async def unstake(self, user_address, protocol):        
        abi = await self._read_abi("./abi/MockStake.json")
        wallet = await self.fetch_data(user_address)
        invocation = wallet.invoke_contract(
            contract_address=await self._get_protocol_ca(protocol),
            abi=abi,
            method="withdrawAll"
        )

        invocation.wait()
        
        return invocation.transaction_hash


    async def _read_abi(self, abi_path):
        with open(abi_path, 'r') as file:
            return orjson.loads(file.read())


    async def _load_existing_data(self):
        if not os.path.exists(self.file_path):
            return []

        with open(self.file_path, 'rb') as file:
            return orjson.loads(file.read())

    async def _save_data(self, data):
        with open(self.file_path, 'wb') as file:
            file.write(orjson.dumps(data, option=orjson.OPT_INDENT_2))
