import websockets
import asyncio
import json

netuid = 19
subnet_hex = hex(netuid)[2:].zfill(2)
chain_endpoint = "wss://entrypoint-finney.opentensor.ai:443"

async def get_burn_regs():
    async with websockets.connect(
        chain_endpoint, ping_interval=None
    ) as ws:
        await ws.send(json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "state_subscribeStorage",
                # Number of burn registrations
                #"params": [[f"0x658faa385070e074c85bf6b568cf055564b6168414916325e7cb4f3f47691e11{subnet_hex}00"]],
                "params": [[f"0x658faa385070e074c85bf6b568cf055501be1755d08418802946bca51b686325{subnet_hex}00"]],
            }
        ))
        ignore = await ws.recv()  # ignore the first response since it's a just a confirmation
        response = await ws.recv()
        full_response = json.loads(response)
        #print(full_response)
        changes_list = full_response["params"]["result"]["changes"]
        print(changes_list)

        # convert little-endian hex to an int
        for changes in changes_list:
            for change_hex in changes:
                try:
                    change = int(change_hex)
                    pass
                    print(f"Change Hex: {change_hex}, Change Value: {change}")
                except Exception as e:
                    pass
            
            #change["value"] = int(change["value"], 16)
            #print(change)            

        #print(changes)
        # then parse the little-endian hex value to an int and you'll get the number of burn registrations this interval

asyncio.run(get_burn_regs())
