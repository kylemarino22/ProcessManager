from sysproduction.update_historical_prices import (
    get_dict_of_instrument_codes_by_timezone,
    get_list_of_instruments_in_region,
    update_historical_prices_for_list_of_instrument_codes
)
from sysdata.tools.cleaner import  get_config_for_price_filtering

from sysdata.data_blob import dataBlob
from sysproduction.data.prices import diagPrices
from sysproduction.data.instruments import diagInstruments
from kyle_tests.price_pipeline.mp_and_adj_api import (
    update_mp_for_instr,
    update_adj_for_instr
)
import argparse




def update_region(region: str):

    assert region in ["US", "ASIA", "EMEA"]
    
    data = dataBlob()
    price_data = diagPrices(data)
    all_instr = price_data.get_list_of_instruments_in_multiple_prices()
    
    region_instr_list = get_list_of_instruments_in_region(
        region=region,
        data=data,
        list_of_instrument_codes=all_instr
    )

    idx = region_instr_list.index('JPY_mini')

    region_instr_list = region_instr_list[idx:]

    update_historical_prices_for_list_of_instrument_codes(
        data,
        region_instr_list,
        full_ib_download=True,
        overwrite=True
    )

    # for instr in region_instr_list:
    #     mp = update_mp_for_instr(instr)
    #     update_adj_for_instr(instr, mp)

    return region_instr_list

    

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Update prices for a specific zone/region.")
    parser.add_argument("--zone", type=str, default="ALL", help="Region to update prices for: US, ASIA, EMEA, or ALL")
    args = parser.parse_args()

    zones = ["US", "ASIA", "EMEA"] if args.zone == "ALL" else [args.zone]

    for zone in zones:
        instruments = update_region(zone)
        print(f"{zone}: {len(instruments)} instruments updated")

    # a = download_for_region("US")
    # print(len(a))
    # b = download_for_region("ASIA")
    # print(len(b))
    # c = download_for_region("EMEA")
    # print(len(c))
    # print(len(a+b+c))