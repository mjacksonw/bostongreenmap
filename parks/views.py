# Views for Parks
from django.core import serializers
from django.views.generic.base import TemplateView
from django.views.generic.list import ListView

from django.contrib.sites.models import Site

from django.contrib.gis.measure import D
from django.utils import simplejson
from django.core.mail import send_mail

from django.template.defaultfilters import slugify
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.http import HttpResponse, Http404, HttpResponseRedirect
from parks.models import Neighborhood, Park, Facility, Activity, Event, Parktype, Story, Facilitytype
from forms import StoryForm
from django.template import RequestContext
from django.conf import settings
from mbta.models import MBTAStop

import json


import cgpolyencode
current_site = Site.objects.get_current()


def get_topnav_data():
    """ Returns lists of all Neighborhoods, Activities and 
        Parks serialized as JSON.
    """
    neighborhoods = Neighborhood.objects.all().only('name')
    activities = Activity.objects.all().only('name')

    return neighborhoods, activities

def get_parks(request):
    """ Returns parks as JSON based search parameters
    """

    querydict = request.GET
    kwargs = querydict.dict()

    try:
        parks = Park.objects.filter(**kwargs)
        parks_json = dict()
        for p in parks:
            parks_json[p.name] = p.get_absolute_url()
        return HttpResponse(json.dumps(parks_json), mimetype='application/json')

    except:
        # no content
        return HttpResponse(status=204)


class HomePageView(TemplateView):

    template_name = 'parks/home.html'

    def get_context_data(self, **kwargs):
        context = super(HomePageView, self).get_context_data(**kwargs)
        context['neighborhoods'], context['activities'] = get_topnav_data()

        return context


class NeighborhoodParkListView(ListView):

    context_object_name = 'park_list'
    template_name = 'parks/neighborhood.html'

    def get_queryset(self):
        self.neighborhood = get_object_or_404(Neighborhood, slug=self.kwargs['slug'])
        return Park.objects.filter(neighborhoods=self.neighborhood)

    def get_context_data(self, **kwargs):
        context = super(NeighborhoodParkListView, self).get_context_data(**kwargs)
        context['neighborhood'] = self.neighborhood
        return context


def parks_page(request, park_slug):
    park = get_object_or_404(Park, slug=park_slug)
    encoder = cgpolyencode.GPolyEncoder()
    coordinates = simplejson.loads(park.geometry.geojson)
    map = encoder.encode(coordinates['coordinates'][0][0])
    stories = Story.objects.filter(park=park).order_by("-date")
    #stops = MBTAStop.objects.filter(lat_long__distance_lte=(park.geometry.centroid,D(mi=settings.MBTA_DISTANCE))) # this distance doesn't overload the page with a million stops.
    
    neighborhoods, activities = get_topnav_data()

    if request.method == 'POST':
        story = Story()
        f = StoryForm(request.POST, instance=story)
        if f.is_valid():
            story.park = park
            f.save()
            f = StoryForm()
    else:
        f = StoryForm()
    return render_to_response('parks/park.html',
        {'park': park,
         'map': map,
         #'stops': stops,
         'story_form': f,
         'stories': stories,
         'request': request,
         'acres': park.geometry.area * 0.000247,
         'neighborhoods': neighborhoods,
         'activities': activities,
        },
        context_instance=RequestContext(request)
    )


#Temporary view to see Play page
def play_page(request):
    neighborhoods = Neighborhood.objects.all().order_by('name')
    activities = Activity.objects.all().order_by('name')
    response_d = {
        'neighborhoods': neighborhoods,
        'activities': activities,
        }

    return render_to_response('parks/play.html', response_d,
        context_instance=RequestContext(request))


def parks_in_neighborhood_with_activities(request, a_slug, n_slug):  # Activity slug, and Neighborhood slug
    activities = Activity.objects.all()
    activity = Activity.objects.get(slug=a_slug)
    neighborhood, parks = get_n_p_with_a(n_slug, a_slug)
    response_d = {
        'neighborhood': neighborhood,
        'activities': activities,
        'activity': activity,
        'a_slug': a_slug,
        'parks': parks}
    return render_to_response('parks/play.html',
        response_d,
        context_instance=RequestContext(request)
)


def get_n_p_with_a(n_slug, a_slug):
    """
    Get parks in a neighborhood that have the specific activity for any of its facilities
    if no request is passed, returns neighborhood and the parks
    """
    a = get_object_or_404(Activity, slug=a_slug)
    fac = Facility.objects.filter(activity=a)
    if n_slug == 'all':
        n = Neighborhood.objects.all()
    else:
        n = get_object_or_404(Neighborhood, slug=n_slug)
    facility_ids = []
    for f in fac:
        facility_ids.append(f.id)
    p = Park.objects.filter(neighborhoods=n, facility__id__in=facility_ids)
    return n, p


def neighborhood_activity_ajax(request, n_slug, a_slug):
    """
    Returns a json string of parks with activities in the specified neighborhood
    """
    try:
        n, parks = get_n_p_with_a(n_slug, a_slug)
    except Http404:
        return HttpResponse("{}")
    parks_json = []
    for park in parks:
        p_dict = {}
        p_dict['activity'] = []
        for f in park.facility_set.all():
            for a in f.activity.all():
                p_dict['activity'].append({'slug': a.slug})
        p_dict['name'] = park.name
        p_dict['slug'] = park.slug
        p_dict['description'] = park.description
        parks_json.append(p_dict)

    return HttpResponse(json.dumps(parks_json))


def events(request, event_id, event_name):
    event = get_object_or_404(Event, pk=event_id)
    return render_to_response('parks/event.html', {'event': event})


def explore(request):  # Activity slug, and Neighborhood slug
    # will be the new home page
    parkname = request.POST.get('parkname',None)
    neighborhoods = Neighborhood.objects.all().order_by('name')
    #activities = Activity.objects.all().order_by('name')
    parks = Park.objects.all().order_by('name')
    facilitytypes = Facilitytype.objects.all().order_by('name')
    neighborhood_slug = request.GET.get('neighborhood', None)
    neighborhood = None
    if neighborhood_slug:
        neighborhood = Neighborhood.objects.get(slug=neighborhood_slug)
    response_d = {
        'neighborhoods': neighborhoods,
        'neighborhoodpassed': neighborhood,
        'facilitytypes':facilitytypes,
        'parks':parks,
        'parkname':parkname,
        }
    return render_to_response('parks/explore.html',
        response_d,
        context_instance=RequestContext(request)
        )


def plan_a_trip(request):  # Activity slug, and Neighborhood slug
    
    return render_to_response('parks/trip.html',
        { },
        context_instance=RequestContext(request)
        )

    
def story(request, story_id):
    story = get_object_or_404(Story, id=story_id)
    return render_to_response('parks/story.html',
        dict(story=story), context_instance=RequestContext(request))


def story_flag(request,story_id):
    story = Story.objects.get(pk=story_id)
    if not story.objectionable_content:
        MESSAGE = """
A user of the Boston Parks website has flagged this story as objectionable.

Here is the story:
{story}

Link to Admin: http://{domain}/admin/parks/story/{id}
""".format(story=story.text,domain=current_site.domain,id=story.id)
        emails = []
        for admin in settings.ADMINS:
            emails.append(admin[1])
        send_mail('Flagged Story on the BostonParks website', MESSAGE, 'support@bostonparks.org',
                emails, fail_silently=False)
        story.objectionable_content = True
        story.save()
    return HttpResponse("")
   
def policy(request):
    return render_to_response('parks/policy.html',
        {}, context_instance=RequestContext(request))


def home_search(request):
    if request.method == "POST":
        parkname = request.POST.get("parkname",None)
        if parkname:
            parkname = slugify(parkname)
            try:
                park = Park.objects.get(slug=parkname)
                if park:
                    return HttpResponseRedirect("/park/%s/" % parkname)
            except Park.DoesNotExist:
                pass
    return HttpResponseRedirect("/")
