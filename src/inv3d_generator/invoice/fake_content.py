import calendar
import datetime
import json
import math
import random
import re
import types
from collections import OrderedDict
from datetime import timedelta
from pathlib import Path
from typing import List, Dict, Set, Any, Union

import dpath.util
import pandas as pd
import phonenumbers
from faker import Faker
from faker.config import AVAILABLE_LOCALES
from faker.providers import phone_number, company, date_time, internet, bank
from schwifty import IBAN, BIC

from .bbox import BoundingBox
from ..util import check_file


class InvoiceContent:

    def __init__(self, assets_dir: Path, max_products: int, shipping_tag: bool, discount_tag: bool):
        self.fake = Faker()
        self.fake.seed_instance(random.getrandbits(32))
        self.fake.add_provider(phone_number)
        self.fake.add_provider(company)
        self.fake.add_provider(date_time)
        self.fake.add_provider(internet)
        self.fake.add_provider(bank)

        self.ecommerce_data = pd.read_csv(str(assets_dir / "ecommerce_data.csv"))
        self.payment_terms_data = pd.read_csv(str(assets_dir / "payment_terms.csv"))

        style = random.choice(["capitalize", "title"])

        tax_rate = round(random.uniform(0.01, 0.2), 3)
        num_products = random.randint(1, max_products)
        identifiers = random.sample(range(10000), k=max_products)
        products = {str(idx): self.fake_product(style, identifier, is_padding=idx >= num_products, tax_rate=tax_rate)
                    for idx, identifier in zip(range(max_products), identifiers)}

        payment_terms = self.fake_payment_terms()
        invoice_date = self.fake.date_between(start_date='-30y', end_date='today')
        invoice_due_date = self.calc_due_date(invoice_date, payment_terms)
        delivery_date = invoice_date + timedelta(days=random.randint(1, 60))
        date_format = random.choice([None, "%m/%d/%Y", "%d %b, %Y", "%d %B, %Y"])

        self.complete_data = {
            "delivery_date": InvoiceContent.format_date(delivery_date, date_format),
            "invoice_date": InvoiceContent.format_date(invoice_date, date_format),
            "invoice_due_date": InvoiceContent.format_date(invoice_due_date, date_format),
            "invoice_number": self.fake_invoice_number(),
            "seller": {
                "contact": self.fake_name(),
                "company": self.fake_company(),
                "address": self.fake_address(),
                "phone_number": self.fake_phone_number(),
                "fax_number": self.fake_phone_number(),
                "email": self.fake.company_email(),
                "website": self.fake.domain_name(),
                "salesperson": self.fake_name()
            },
            "buyer": {
                "company": self.fake_company(),
                "website": self.fake.domain_name(),
                "shipment": {
                    "contact": self.fake_name(),
                    "address": self.fake_address(),
                    "phone_number": self.fake_phone_number(),
                    "fax_number": self.fake_phone_number(),
                    "email": self.fake.company_email(),
                    "customer_id": self.fake_customer_id()
                },
                "bill": {
                    "contact": self.fake_name(),
                    "address": self.fake_address(),
                    "phone_number": self.fake_phone_number(),
                    "fax_number": self.fake_phone_number(),
                    "email": self.fake.company_email(),
                    "customer_id": self.fake_customer_id()
                }
            },
            "products": products,
            "summary": self.fake_summary(products, shipping_tag, discount_tag=discount_tag, tax_rate=tax_rate),
            "payment_terms": payment_terms,
            "beneficiary": self.fake_beneficiary()
        }

        self.all_attributes = self.collapse_data()

    def subset_data(self, queries: Set[str], output_file: Path = None):

        # build subset of "self.complete_data" defined by the combination of all queries
        result = {}
        for query in queries:
            tmp = dpath.util.search(self.complete_data, query, separator='.', afilter=lambda x: x is not None)
            result = dpath.util.merge(result, tmp)

        # filter __str__ attributes
        if len(list(dpath.util.search(result, "**.__str__", separator='.', yielded=True))) > 0:
            dpath.util.delete(result, "**.__str__", separator='.')

        # move __val__ attributes one layer higher
        matches = list(dpath.util.search(result, "**.__val__", separator='.', yielded=True))
        for path, value in matches:
            parent_path = '.'.join(path.split(".")[:-1])

            _, parent_value = list(dpath.util.search(result, parent_path, separator='.', yielded=True))[0]
            assert len(parent_value) == 1, "Value attributes '__val__' cannot have sibling data fields!"

            dpath.util.set(result, parent_path, value, separator='.')

        if output_file is not None:
            assert output_file.suffix == ".json"

            with output_file.open("w") as f:
                json.dump(result, f, indent=4, sort_keys=True)

        return result

    def collapse_data(self, output_file: Path = None):
        data = {path: value for path, value in
                dpath.util.search(self.complete_data, "**", separator='.', yielded=True, dirs=False)}

        data = {path[:-len(".__str__")] if path.endswith(".__str__") else path: value
                for path, value in data.items()
                if not path.endswith("__val__")}

        if output_file is not None:
            assert output_file.suffix == ".json"

            with output_file.open("w") as f:
                json.dump(data, f, indent=4, sort_keys=True)

        return data

    def export_complete_data(self, file: Path):
        assert file.suffix == ".json"

        with file.open("w") as f:
            json.dump(self.complete_data, f, indent=4, sort_keys=True)

    def fake_beneficiary(self):
        iban, bic = None, None
        while True:
            try:
                iban = IBAN(self.fake.iban())
                bic = BIC.from_bank_code(country_code=iban.country_code, bank_code=iban.bank_code)
            except ValueError:
                pass

            if bic is None:
                continue

            break

        return {
            "name": self.fake_name(),
            "iban": {
                "__str__": iban.formatted,
                "country_code": iban.country_code,
                "account_code": iban.account_code,
                "bank_code": iban.bank_code,
                "branch_code": iban.branch_code
            },
            "bic": {
                "__str__": bic.formatted,
                "country_code": bic.country_code,
                "location_code": bic.location_code,
                "bank_code": bic.bank_code,
                "branch_code": bic.branch_code,
            },
            "bank": {
                "name": self.fake.company(),
                "address": self.fake_address()
            }
        }

    def fake_address(self):
        address = self.inject_faker("address", ['street_name', 'city'])

        if "military_state" in list(address.keys()):
            return self.fake_address()  # retry

        # make assumptions about returned address for restructuring
        assert set(address.keys()) == {"__str__", "city", "postcode", "state_abbr", "street_address"}

        lines = address["__str__"].split("\n")
        assert len(lines) == 2
        assert lines[0] == address["street_address"]["__str__"]

        return {
            "__str__": address["__str__"],
            "city": {
                "__str__": lines[1],
                "city_name": address["city"],
                "postcode": address["postcode"],
                "state_abbr": address["state_abbr"]
            },
            "street": address["street_address"],
        }

    def fake_company(self):
        return {
            "name": self.fake.company(),
            "slogan": self.fake.catch_phrase()
        }

    def fake_phone_number(self):
        international_fake = Faker(random.choice(AVAILABLE_LOCALES))
        international_fake.seed_instance(random.getrandbits(32))
        international_fake.add_provider(phone_number)

        for _ in range(100):
            try:
                number_str = international_fake.phone_number()
                parsed_number = phonenumbers.parse(number_str, "US")  # default country is the USA
                if phonenumbers.is_valid_number(parsed_number):
                    result = {
                        "__str__": number_str,
                        "country_code": self.format_value(parsed_number.country_code, format_string="{}"),
                        "national_number": self.format_value(parsed_number.national_number, format_string="{}"),
                    }
                    if parsed_number.extension is not None:
                        result["extension"] = self.format_value(int(parsed_number.extension), format_string="{}")
                    return result
            except phonenumbers.phonenumberutil.NumberParseException:
                pass  # retry another phone number representation
            except AttributeError:
                return self.fake_phone_number()  # phone_number does not support this locale (reset locale)

        # no valid number found in the last 100 attempts (reset locale)
        return self.fake_phone_number()

    def fake_name(self):
        def remove_suffix(dictionary: Dict, suffix: str):
            dictionary = {key[:-len(suffix)] if key.endswith(suffix) else key: value
                          for key, value in dictionary.items()}
            dictionary = {key: remove_suffix(value, suffix) if isinstance(value, dict) else value
                          for key, value in dictionary.items()}
            return dictionary

        def remove_suffixes(dictionary: Dict, suffixes: List[str]):
            for suffix in suffixes:
                dictionary = remove_suffix(dictionary, suffix=suffix)
            return dictionary

        return remove_suffixes(self.inject_faker("name"), suffixes=["_male", "_female"])

    def inject_faker(self, method_name: str, final_formatters: List[str] = None):

        if final_formatters is None:
            final_formatters = []

        collection = OrderedDict()

        def parse_inject(_self, text):
            mapping = {}

            def wrapper(matches):
                formatter = list(matches.groups())[0]
                assert formatter not in mapping
                mapping[formatter] = _self._Generator__format_token(matches)
                return mapping[formatter]

            _re_token = re.compile(r'{{\s*(\w+)(:\s*\w+?)?\s*}}')
            formatted = _re_token.sub(wrapper, text)

            mapping["__str__"] = formatted
            mapping = {key: collection[value] if value in collection and key not in final_formatters else value
                       for key, value in mapping.items()}

            collection[formatted] = mapping
            return formatted

        # gather factory
        factories = self.fake._factories
        assert len(factories) == 1
        factory = factories[0]

        parse_old = factory.parse  # save old parse method
        factory.parse = types.MethodType(parse_inject, factory)  # replace parse method
        getattr(self.fake, method_name)()  # trigger method execution
        factory.parse = parse_old  # restore old method

        return collection[list(collection.keys())[-1]]

    def calc_due_date(self, invoice_date: date_time.date, payment_terms: Dict):
        due_offset = \
            self.payment_terms_data[self.payment_terms_data['Abbreviation'] == payment_terms["__val__"]].iloc[0][
                'DueOffset']

        if isinstance(due_offset, float) and math.isnan(due_offset):
            return None

        if isinstance(due_offset, int) or (isinstance(due_offset, str) and due_offset.isdigit()):
            due_offset = int(due_offset)
            return invoice_date + timedelta(days=due_offset)

        year = invoice_date.year
        month = invoice_date.month + 1

        if month == 13:
            year += 1
            month = 1

        if due_offset == "eom":
            last_day = calendar.monthrange(year, month)[1]
            return datetime.datetime(year, month, last_day)

        if due_offset == "21mfi":
            return datetime.datetime(year, month, 21)

        print(f"WARNING: unknown due date offset '{due_offset}'")
        return None

    @staticmethod
    def format_date(date, date_format: str):
        if date is None:
            return {
                "__str__": "-",
                "__val__": None
            }

        return {
            "__str__": str(date) if date_format is None else date.strftime(date_format),
            "day": InvoiceContent.format_value(value=date.day, format_string="{}"),
            "month": InvoiceContent.format_value(value=date.month, format_string="{}"),
            "year": InvoiceContent.format_value(value=date.year, format_string="{}")
        }

    def fake_payment_terms(self):
        terms_idx = random.randrange(self.payment_terms_data.shape[0])
        terms = self.payment_terms_data.iloc[terms_idx]
        return {
            "__str__": terms.PaymentTerm,
            "__val__": terms.Abbreviation
        }

    @staticmethod
    def fake_invoice_number():
        return InvoiceContent.format_value(value=random.randint(1000, 1000000), format_string="#{}")

    @staticmethod
    def fake_customer_id():
        return InvoiceContent.format_value(value=random.randint(100000, 10000000), format_string="{}")

    def fake_product(self, description_style: str, identifier: int, tax_rate: float, is_padding: bool = False):
        assert description_style in ["capitalize", "title"]

        if is_padding:
            return {
                'id': None,
                'description': None,
                'quantity': None,
                'unit_price': None,
                'tax_rate': None,
                'total': None
            }

        product = self.ecommerce_data.sample().iloc[0]

        # avoid rare error in data
        while not isinstance(product.Description, str):
            product = self.ecommerce_data.sample().iloc[0]

        quantity = random.randint(1, 10)
        unit_price = product.UnitPrice
        description = product.Description.capitalize() if description_style == "capitalize" else product.Description.title()
        total = round(quantity * unit_price, 2)

        return {
            'id': InvoiceContent.format_value(value=identifier, format_string="{}"),
            'description': description,
            'quantity': InvoiceContent.format_value(value=quantity, format_string="{}"),
            'unit_price': InvoiceContent.format_value(value=unit_price, format_string="{:.2f}"),
            'tax_rate': InvoiceContent.format_value(value=tax_rate, format_string="{:.1%}"),
            'total': InvoiceContent.format_value(value=total, format_string="{:.2f}")
        }

    @staticmethod
    def fake_summary(products: Dict, shipping_tag: bool, discount_tag: bool, tax_rate: float):
        subtotal = round(sum(product["total"]["__val__"]
                             for product in products.values()
                             if product["total"] is not None), 2)
        discount = round(random.uniform(0, min(subtotal, 100)), 2) if discount_tag and random.random() < 0.5 else 0
        subtotal_less_discount = round(subtotal - discount, 2)
        tax_total = round(subtotal_less_discount * tax_rate, 2)
        shipping = round(random.uniform(1, 10), 2) if shipping_tag else 0
        balance = round(subtotal_less_discount + tax_total + shipping, 2)

        return {
            "subtotal": InvoiceContent.format_value(value=subtotal, format_string="{:.2f}"),
            "discount": InvoiceContent.format_value(value=discount, format_string="{:.2f}"),
            "subtotal_less_discount": InvoiceContent.format_value(value=subtotal_less_discount, format_string="{:.2f}"),
            'tax_rate': InvoiceContent.format_value(value=tax_rate, format_string="{:.1%}"),
            'tax_total': InvoiceContent.format_value(value=tax_total, format_string="{:.2f}"),
            'shipping': {
                'price': InvoiceContent.format_value(value=shipping, format_string="{:.2f}"),
                'method': random.choice(["UPS", "USPS", "DHL", "FedEx"])
            },
            'balance': InvoiceContent.format_value(value=balance, format_string="$ {:.2f}"),
        }

    @staticmethod
    def format_value(value: Any, format_string: Union[str, None]):
        return {
            "__str__": "" if format_string is None else format_string.format(value),
            "__val__": value
        }

    def export_ground_truth(self, output_dir: Path, template_fields: List[BoundingBox]):

        # export structured data subset
        ground_truth_structure_file = output_dir / "ground_truth_structure.json"
        self.subset_data(queries=set(bbox.name for bbox in template_fields), output_file=ground_truth_structure_file)

        # export bounding boxes
        def to_json(bbox):
            return {
                "tag": bbox.name,
                "value": self.all_attributes[bbox.name],
                "top": int(bbox.top),
                "left": int(bbox.left),
                "height": int(bbox.height),
                "width": int(bbox.width)
            }

        json_boxes = [to_json(bbox) for bbox in template_fields if bbox.name in self.all_attributes]
        json_boxes = [json_bbox for json_bbox in json_boxes if json_bbox["value"] is not None]
        json_boxes = sorted(json_boxes, key=lambda x: x["tag"])

        ground_truth_bbox_file = output_dir / "ground_truth_tags.json"
        with ground_truth_bbox_file.open("w") as f:
            json.dump(json_boxes, f, indent=4)

    @staticmethod
    def visualize(json_file: Path, background_file: Path, output_file: Path):
        check_file(json_file, ".json")
        check_file(background_file, ".png")
        check_file(output_file, ".png", exist=None)

        with json_file.open("r") as f:
            bboxes = [BoundingBox(top=data["top"],
                                  left=data["left"],
                                  height=data["height"],
                                  width=data["width"],
                                  name=data["tag"]) for data in json.load(f)]

        BoundingBox.visualize(bboxes=bboxes, input_file=background_file, output_file=output_file)
