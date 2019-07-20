import os
import requests
import datetime
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.transports import Transport
from .models import WebSalesShipment, User, Region, LastImportedWebSalesShipmentNo
from .utils import generate_random_email
from django.db.models import Max

class NavWrapper(object):
    """Download new entries in Navision web_sales_shipment to local

    Make a soap request to navision using '/Page/WebSalesShipment' endpoint.
    The soap request will return a list of objects, for each object, save in WebSalesShipmetn table
    """
    def __init__(self):
        """Set up variables to be used in class.
        """
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(os.getenv('NAV_USERNAME'), os.getenv('NAV_PASSWORD'))
        base_url = os.getenv('NAV_BASE_URL')
        eu_store_url = os.getenv('NAV_EU_STORE')
        us_store_url = os.getenv('NAV_US_STORE')
        web_sales_shipment_endpint = '/Page/WebSalesShipment'

        self.eu_url = base_url + eu_store_url + web_sales_shipment_endpint
        self.us_url = base_url + us_store_url + web_sales_shipment_endpint

    def get_web_sales_shipments(self, region:str, latest_order_num:int)->Client:
        """Initialize a client with right store url and filter.

        The client will have 2 filters.
            1.Filter for the WebSalesShipment ShipmentDate, since we only interested the order
                that has shipped more than 4 weeks (we don't want to send a nps email to customer
                who only got it few days ago). we only download the order which the shipment date is
                30 days ago to 365 days ago.
            2.Filter for WebSalesShipment['No'], each shipment has an unique 'No', we save the max
                'No' we downloaded, next time when we download from Nav, we only want the orders has
                a greater number than what we already have.

        Arguments:
            region {str} -- Region name e.g. 'eu' or 'us'.
            latest_order_num {int} -- 'No' for the last imported web sales shipment.

        Returns:
            Client -- zeep client to make soap request to Nav.
        """
        a_year_ago = (datetime.date.today() - datetime.timedelta(365)).strftime('%m%d%Y')
        a_month_ago = (datetime.date.today() - datetime.timedelta(30)).strftime('%m%d%Y')

        id_filter = {
            "Field": "No",
            "Criteria" : f">{latest_order_num}"
        }
        date_filter = {
            "Field": "Shipment_Date",
            "Criteria" :f"{a_year_ago}..{a_month_ago}"
        }

        endpoint_url = self.get_endpoint_url(region)

        client = Client(endpoint_url, transport=Transport(session=self.session))

        results = client.service.ReadMultiple(
                    filter = [id_filter, date_filter],
                    bookmarkKey = None,
                    setSize = '',
                )

        return results

    def store_all_regions_sales_shipment(self) -> bool:
        """Get all regions object, for each region, call "store_web_sales_shipment()" method.

        Returns:
            bool -- True if all region's shipment downloaded successfuly, False otherwise
        """
        try:
            all_regions = Region.objects.all()
            for region in all_regions:
                self.store_web_sales_shipment(region)
            return True
        except Exception as e:
            print(e)
            return False

    def store_web_sales_shipment(self, region: object) -> None:
        """For the given region, make soap request and get WebSalesShipment data from Navision,
        for each shipment, save in the web_sales_shipment table and update the last imported 'No'
        for that region. The number is saved in LastImportedWebSalesShipmentNo table.

        Arguments:
            region {object} -- region object.

        Returns:
            None
        """
        max_order_num = self.get_last_order_num(region)
        shipments = self.get_web_sales_shipments(region, max_order_num)

        if shipments is None:
            print(f"No new Web Sales Shipmnts from {region.name}")
            return

        for shipment in shipments:
            email = generate_random_email()

            user_inst, created = User.objects.get_or_create(email=email)

            try:
                web_sales_shipment = WebSalesShipment.objects.create(
                    number = shipment['No'],
                    shipment_date = shipment['Shipment_Date'],
                    user = user_inst,
                    region = region,
                )
                if int(shipment['No']) > max_order_num:
                    max_order_num = int(shipment['No'])
            except Exception as e:
                print(e)
                break

        self.update_max_order_num_imported(region, max_order_num)
        shipments_count = str(len(shipments))
        print(f"{shipments_count} {region.name} Web Sales Shipments have been imported")
        return

    def update_max_order_num_imported(self, region: object, latest_order_num: int) -> None:
        """Update the max 'No' (like id) of web sales shipment for the region

        Arguments:
            region {object} -- Region object
            latest_order_num {int} -- The max 'No' number of a web sales shipment downloaded

        Returns:
            None
        """
        try:
            last_import_inst = LastImportedWebSalesShipmentNo.objects.get(region=region)
            last_import_inst.last_import_no = latest_order_num
            last_import_inst.save()
        except Exception as e:
            print(e)

    def get_last_order_num(self, region: object) -> int:
        """Get the last_import_no for the region, if no entry found, get all WebSalesShipment for
        that region, calculate the max 'No' and save it in LastImportedWebSalesShipmentNo table

        Arguments:
            region {object} -- Single region object.

        Returns:
            int -- The last import number for the given region.
        """
        try:
            last_import_inst = LastImportedWebSalesShipmentNo.objects.get(region=region)
        except LastImportedWebSalesShipmentNo.DoesNotExist:
            last_import_inst = LastImportedWebSalesShipmentNo()
            last_import_inst.region = region
            last_number = WebSalesShipment.objects.aggregate(Max('number'))
            last_import_inst.last_import_no = int(last_number["number__max"])
            last_import_inst.save()
        return last_import_inst.last_import_no

    def get_endpoint_url(self, region: object) -> str or False:
        """Get the Navision store url for the region

        Arguments:
            region {object} -- Single region object

        Returns:
            str or False -- Returns the url as string, or print "Incorrect region found! Please
            update db if new region is added!" in the console and return false.
        """
        if region.name == 'eu':
            return self.eu_url
        elif region.name == "us":
            return self.us_url
        else:
            # raise exception region not found, read python custom exceptions/errors
            print("Incorrect region found! Please update db if new region is added!")
            return False
