# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.CORE
#
# Copyright 2018 by it's authors.
# Some rights reserved. See LICENSE.rst, CONTRIBUTORS.rst.

from bika.lims import api
from bika.lims import bikaMessageFactory as _
from bika.lims.browser import BrowserView
from bika.lims.browser.worksheet.tools import showRejectionMessage
from bika.lims.config import WORKSHEET_LAYOUT_OPTIONS
from bika.lims.utils import getUsers
from plone.app.layout.globals.interfaces import IViewView
from Products.Archetypes.public import DisplayList
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import safe_unicode
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.interface import implements
from plone.memoize import view
from bika.lims.permissions import EditWorksheet
from bika.lims.permissions import ManageWorksheets


class ManageResultsView(BrowserView):
    """Worksheet Manage Results View
    """
    implements(IViewView)
    template = ViewPageTemplateFile("../templates/results.pt")

    def __init__(self, context, request):
        super(ManageResultsView, self).__init__(context, request)
        self.icon = "{}/{}".format(
            self.portal_url,
            "/++resource++bika.lims.images/worksheet_big.png"
        )

        self.layout_displaylist = WORKSHEET_LAYOUT_OPTIONS

    def __call__(self):
        # TODO: Refactor Worfklow
        if not self.is_edit_allowed():
            redirect_url = api.get_url(self.context)
            return self.request.response.redirect(redirect_url)
        # TODO: Refactor this function call
        showRejectionMessage(self.context)

        # Save the results layout
        rlayout = self.request.get("resultslayout", "")
        if rlayout and rlayout in WORKSHEET_LAYOUT_OPTIONS.keys() \
           and rlayout != self.context.getResultsLayout():
            self.context.setResultsLayout(rlayout)
            message = _("Changes saved.")
            self.context.plone_utils.addPortalMessage(message, "info")

        # Classic/Transposed View Switch
        if self.context.getResultsLayout() == "1":
            view = "analyses_classic_view"
            self.Analyses = api.get_view(
                view, context=self.context, request=self.request)
        else:
            view = "analyses_transposed_view"
            self.Analyses = api.get_view(
                view, context=self.context, request=self.request)

        self.analystname = self.context.getAnalystName()
        self.instrumenttitle = self.get_instrument_title()

        # Check if the instruments used are valid
        self.checkInstrumentsValidity()

        return self.template()

    def get_analysts(self):
        """Returns Analysts
        """
        roles = ["Manager", "LabManager", "Analyst"]
        return getUsers(self.context, roles)

    @view.memoize
    def get_instrument_title(self):
        """Return the current instrument title
        """
        instrument = self.context.getInstrument()
        if not instrument:
            return ""
        return api.get_title(instrument)

    @view.memoize
    def is_edit_allowed(self):
        """Check if edit is allowed
        """
        checkPermission = self.context.portal_membership.checkPermission
        return checkPermission(EditWorksheet, self.context)

    @view.memoize
    def is_manage_allowed(self):
        """Check if manage is allowed
        """
        checkPermission = self.context.portal_membership.checkPermission
        return checkPermission(ManageWorksheets, self.context)

    @view.memoize
    def is_assignment_allowed(self):
        """Check if analyst assignment is allowed
        """
        if not self.is_manage_allowed():
            return False
        review_state = api.get_workflow_status_of(self.context)
        edit_states = ["open", "attachment_due", "to_be_verified"]
        return review_state in edit_states

    def getInstruments(self):
        # TODO: Return only the allowed instruments for at least one contained
        # analysis
        bsc = getToolByName(self, 'bika_setup_catalog')
        items = [('', '')] + [(o.UID, o.Title) for o in
                              bsc(portal_type='Instrument',
                                  inactive_state='active')]
        o = self.context.getInstrument()
        if o and o.UID() not in [i[0] for i in items]:
            items.append((o.UID(), o.Title()))
        items.sort(lambda x, y: cmp(x[1].lower(), y[1].lower()))
        return DisplayList(list(items))

    def get_wide_interims(self):
        """Returns a dictionary with the analyses services from the current
        worksheet which have at least one interim with 'Wide' attribute set to
        true and that have not been yet submitted

        The structure of the returned dictionary is the following:
        <Analysis_keyword>: {
            'analysis': <Analysis_name>,
            'keyword': <Analysis_keyword>,
            'interims': {
                <Interim_keyword>: {
                    'value': <Interim_default_value>,
                    'keyword': <Interim_key>,
                    'title': <Interim_title>
                }
            }
        }
        """
        outdict = {}
        allowed_states = ['assigned', 'unassigned']
        for analysis in self.context.getAnalyses():
            # TODO Workflow - Analysis Use a query instead of this
            if api.get_workflow_status_of(analysis) not in allowed_states:
                continue

            if analysis.getKeyword() in outdict.keys():
                continue

            calculation = analysis.getCalculation()
            if not calculation:
                continue

            andict = {
                "analysis": analysis.Title(),
                "keyword": analysis.getKeyword(),
                "interims": {}
            }

            # Analysis Service interim defaults
            for field in analysis.getInterimFields():
                if field.get("wide", False):
                    andict["interims"][field["keyword"]] = field

            # Interims from calculation
            for field in calculation.getInterimFields():
                if field["keyword"] not in andict["interims"].keys() \
                   and field.get("wide", False):
                    andict["interims"][field["keyword"]] = field

            if andict["interims"]:
                outdict[analysis.getKeyword()] = andict
        return outdict

    def checkInstrumentsValidity(self):
        """Checks the validity of the instruments used in the Analyses If an
        analysis with an invalid instrument (out-of-date or with calibration
        tests failed) is found, a warn message will be displayed.
        """
        invalid = []
        ans = self.context.getAnalyses()
        for an in ans:
            valid = an.isInstrumentValid()
            if not valid:
                instrument = an.getInstrument()
                inv = "%s (%s)" % (
                    safe_unicode(an.Title()), safe_unicode(instrument.Title()))
                if inv not in invalid:
                    invalid.append(inv)
        if len(invalid) > 0:
            message = _("Some analyses use out-of-date or uncalibrated "
                        "instruments. Results edition not allowed")
            message = "%s: %s" % (message, (", ".join(invalid)))
            self.context.plone_utils.addPortalMessage(message, "warning")
