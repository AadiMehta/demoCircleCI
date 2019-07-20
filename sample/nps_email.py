from datetime import date, timedelta, datetime
from score.models import WebSalesShipment, ScoreRequest
from .models import User
from django.core.mail import send_mail
from django.template import loader
import mandrill
import os
from nps.settings import BASE_URL


class NPSEmail:
    """Initialize an object with send method.
    """
    def __init__(self):
        """Pre-calculate the date which is 6 months(180 days) ago
        """
        self.half_year_ago = date.today() - timedelta(180)

    def send(self) -> bool:
        """Take all web sales shipment which nps_status is 'pending', find the user attached to this
        shipment, validate the user's accepts_survey/last_nps_email_send_at and
        last_nps_email_answered_at, for the remaining user, send them nps email and update the
        last_nps_email_send_at to today. If the user has send/answered in the past 6 month,
        change the shipment nps_status to 'shipped'


        Returns:
            None -- If the email is send and shipment.nps_status is updated
            False -- If the user.accepts_survey == False, or there is an Exception
        """
        """
            if never sent mail                  --> send the mail
            if mail sent but not answered       -->
                        A. if mail sent more than 6 months ago --> send mail
                        B. Else do not send mail --> update shipment to 'skipped'
            if mail sent and answered           ->>
                        A. if answered_data is more than 6 months ago  --> send mail
                        B. Else skip and update shipment to 'skipped'
        """
        shipments = WebSalesShipment.objects.filter(nps_status='pending')

        for shipment in shipments:
            try:
                if shipment.user.surveyable:
                    score_request = ScoreRequest.objects.create(user = shipment.user, web_sales_shipment = shipment)
                    self.send_nps_email(score_request)
                    shipment.nps_status = 'sent'
                    shipment.save()
                else:
                    shipment.nps_status = 'skipped'
                    shipment.save()
            except Exception as e:
                print(e)
                return False

    def send_nps_email(self, score_request: object) -> str:
        """Sends a NPS email to the user of ScoreRequest object.

        Arguments:
            score_request {object} -- Single ScoreRequest object..

        Returns:
            str -- Print in console "NPS email has been sent to user@example.com".
        """
        nps_score = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']
        html_message = loader.render_to_string(
                'score/nps_email.html',
                {
                    'id': str(score_request.uuid),
                    'base_url': str(BASE_URL),
                    'nps_score': nps_score
                }
            )
        recipient = score_request.user.email

        if score_request.user.region.name=='us':
            from_name = 'Theresa at Hem '
        else:
            from_name = 'Mathilda at Hem'

        send_mail(
            subject='What do you think about Hem? Two quick questions to help us improve!',
            message = '',
            from_email = 'rsvp@hem.com',
            from_name = from_name,
            recipient_list = [recipient],
            fail_silently=False,
            html_message = html_message
        )
        self.update_user_nps_survey_date(score_request.user.pk)
        print(f"NPS email has been sent to {recipient}")

    def update_user_nps_survey_date(self, user_id: int) -> None:
        """Updates a user's last_nps_email_send_at attribute to today.

        Arguments:
            user_id {int} -- User's primary key.

        Returns:
            None -- Saves the user and returns nothing.
        """
        user = User.objects.get(pk=user_id)
        user.nps_survey_date = date.today()
        user.save()
