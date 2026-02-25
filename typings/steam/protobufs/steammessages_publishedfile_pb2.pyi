import steammessages_base_pb2 as _steammessages_base_pb2
import steammessages_unified_base_pb2 as _steammessages_unified_base_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import service as _service
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EPublishedFileRevision(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_EPublishedFileRevision_Default: _ClassVar[EPublishedFileRevision]
    k_EPublishedFileRevision_Latest: _ClassVar[EPublishedFileRevision]
    k_EPublishedFileRevision_ApprovedSnapshot: _ClassVar[EPublishedFileRevision]
    k_EPublishedFileRevision_ApprovedSnapshot_China: _ClassVar[EPublishedFileRevision]
    k_EPublishedFileRevision_RejectedSnapshot: _ClassVar[EPublishedFileRevision]
    k_EPublishedFileRevision_RejectedSnapshot_China: _ClassVar[EPublishedFileRevision]

class EPublishedFileForSaleStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    k_PFFSS_NotForSale: _ClassVar[EPublishedFileForSaleStatus]
    k_PFFSS_PendingApproval: _ClassVar[EPublishedFileForSaleStatus]
    k_PFFSS_ApprovedForSale: _ClassVar[EPublishedFileForSaleStatus]
    k_PFFSS_RejectedForSale: _ClassVar[EPublishedFileForSaleStatus]
    k_PFFSS_NoLongerForSale: _ClassVar[EPublishedFileForSaleStatus]
    k_PFFSS_TentativeApproval: _ClassVar[EPublishedFileForSaleStatus]
k_EPublishedFileRevision_Default: EPublishedFileRevision
k_EPublishedFileRevision_Latest: EPublishedFileRevision
k_EPublishedFileRevision_ApprovedSnapshot: EPublishedFileRevision
k_EPublishedFileRevision_ApprovedSnapshot_China: EPublishedFileRevision
k_EPublishedFileRevision_RejectedSnapshot: EPublishedFileRevision
k_EPublishedFileRevision_RejectedSnapshot_China: EPublishedFileRevision
k_PFFSS_NotForSale: EPublishedFileForSaleStatus
k_PFFSS_PendingApproval: EPublishedFileForSaleStatus
k_PFFSS_ApprovedForSale: EPublishedFileForSaleStatus
k_PFFSS_RejectedForSale: EPublishedFileForSaleStatus
k_PFFSS_NoLongerForSale: EPublishedFileForSaleStatus
k_PFFSS_TentativeApproval: EPublishedFileForSaleStatus

class CPublishedFile_Vote_Request(_message.Message):
    __slots__ = ("publishedfileid", "vote_up")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    VOTE_UP_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    vote_up: bool
    def __init__(self, publishedfileid: _Optional[int] = ..., vote_up: _Optional[bool] = ...) -> None: ...

class CPublishedFile_Vote_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_Subscribe_Request(_message.Message):
    __slots__ = ("publishedfileid", "list_type", "appid", "notify_client")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    LIST_TYPE_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    NOTIFY_CLIENT_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    list_type: int
    appid: int
    notify_client: bool
    def __init__(self, publishedfileid: _Optional[int] = ..., list_type: _Optional[int] = ..., appid: _Optional[int] = ..., notify_client: _Optional[bool] = ...) -> None: ...

class CPublishedFile_Subscribe_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_Unsubscribe_Request(_message.Message):
    __slots__ = ("publishedfileid", "list_type", "appid", "notify_client")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    LIST_TYPE_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    NOTIFY_CLIENT_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    list_type: int
    appid: int
    notify_client: bool
    def __init__(self, publishedfileid: _Optional[int] = ..., list_type: _Optional[int] = ..., appid: _Optional[int] = ..., notify_client: _Optional[bool] = ...) -> None: ...

class CPublishedFile_Unsubscribe_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_CanSubscribe_Request(_message.Message):
    __slots__ = ("publishedfileid",)
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    def __init__(self, publishedfileid: _Optional[int] = ...) -> None: ...

class CPublishedFile_CanSubscribe_Response(_message.Message):
    __slots__ = ("can_subscribe",)
    CAN_SUBSCRIBE_FIELD_NUMBER: _ClassVar[int]
    can_subscribe: bool
    def __init__(self, can_subscribe: _Optional[bool] = ...) -> None: ...

class CPublishedFile_GetSubSectionData_Request(_message.Message):
    __slots__ = ("publishedfileid", "for_table_of_contents", "specific_sectionid", "desired_revision")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    FOR_TABLE_OF_CONTENTS_FIELD_NUMBER: _ClassVar[int]
    SPECIFIC_SECTIONID_FIELD_NUMBER: _ClassVar[int]
    DESIRED_REVISION_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    for_table_of_contents: bool
    specific_sectionid: int
    desired_revision: EPublishedFileRevision
    def __init__(self, publishedfileid: _Optional[int] = ..., for_table_of_contents: _Optional[bool] = ..., specific_sectionid: _Optional[int] = ..., desired_revision: _Optional[_Union[EPublishedFileRevision, str]] = ...) -> None: ...

class PublishedFileSubSection(_message.Message):
    __slots__ = ("sectionid", "title", "description_text", "sort_order")
    SECTIONID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_TEXT_FIELD_NUMBER: _ClassVar[int]
    SORT_ORDER_FIELD_NUMBER: _ClassVar[int]
    sectionid: int
    title: str
    description_text: str
    sort_order: int
    def __init__(self, sectionid: _Optional[int] = ..., title: _Optional[str] = ..., description_text: _Optional[str] = ..., sort_order: _Optional[int] = ...) -> None: ...

class CPublishedFile_GetSubSectionData_Response(_message.Message):
    __slots__ = ("sub_sections",)
    SUB_SECTIONS_FIELD_NUMBER: _ClassVar[int]
    sub_sections: _containers.RepeatedCompositeFieldContainer[PublishedFileSubSection]
    def __init__(self, sub_sections: _Optional[_Iterable[_Union[PublishedFileSubSection, _Mapping]]] = ...) -> None: ...

class CPublishedFile_Publish_Request(_message.Message):
    __slots__ = ("appid", "consumer_appid", "cloudfilename", "preview_cloudfilename", "title", "file_description", "file_type", "consumer_shortcut_name", "youtube_username", "youtube_videoid", "visibility", "redirect_uri", "tags", "collection_type", "game_type", "url")
    APPID_FIELD_NUMBER: _ClassVar[int]
    CONSUMER_APPID_FIELD_NUMBER: _ClassVar[int]
    CLOUDFILENAME_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_CLOUDFILENAME_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    FILE_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    FILE_TYPE_FIELD_NUMBER: _ClassVar[int]
    CONSUMER_SHORTCUT_NAME_FIELD_NUMBER: _ClassVar[int]
    YOUTUBE_USERNAME_FIELD_NUMBER: _ClassVar[int]
    YOUTUBE_VIDEOID_FIELD_NUMBER: _ClassVar[int]
    VISIBILITY_FIELD_NUMBER: _ClassVar[int]
    REDIRECT_URI_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    COLLECTION_TYPE_FIELD_NUMBER: _ClassVar[int]
    GAME_TYPE_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    appid: int
    consumer_appid: int
    cloudfilename: str
    preview_cloudfilename: str
    title: str
    file_description: str
    file_type: int
    consumer_shortcut_name: str
    youtube_username: str
    youtube_videoid: str
    visibility: int
    redirect_uri: str
    tags: _containers.RepeatedScalarFieldContainer[str]
    collection_type: str
    game_type: str
    url: str
    def __init__(self, appid: _Optional[int] = ..., consumer_appid: _Optional[int] = ..., cloudfilename: _Optional[str] = ..., preview_cloudfilename: _Optional[str] = ..., title: _Optional[str] = ..., file_description: _Optional[str] = ..., file_type: _Optional[int] = ..., consumer_shortcut_name: _Optional[str] = ..., youtube_username: _Optional[str] = ..., youtube_videoid: _Optional[str] = ..., visibility: _Optional[int] = ..., redirect_uri: _Optional[str] = ..., tags: _Optional[_Iterable[str]] = ..., collection_type: _Optional[str] = ..., game_type: _Optional[str] = ..., url: _Optional[str] = ...) -> None: ...

class CPublishedFile_Publish_Response(_message.Message):
    __slots__ = ("publishedfileid", "redirect_uri")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    REDIRECT_URI_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    redirect_uri: str
    def __init__(self, publishedfileid: _Optional[int] = ..., redirect_uri: _Optional[str] = ...) -> None: ...

class CPublishedFile_GetDetails_Request(_message.Message):
    __slots__ = ("publishedfileids", "includetags", "includeadditionalpreviews", "includechildren", "includekvtags", "includevotes", "short_description", "includeforsaledata", "includemetadata", "language", "return_playtime_stats", "appid", "strip_description_bbcode", "desired_revision", "includereactions")
    PUBLISHEDFILEIDS_FIELD_NUMBER: _ClassVar[int]
    INCLUDETAGS_FIELD_NUMBER: _ClassVar[int]
    INCLUDEADDITIONALPREVIEWS_FIELD_NUMBER: _ClassVar[int]
    INCLUDECHILDREN_FIELD_NUMBER: _ClassVar[int]
    INCLUDEKVTAGS_FIELD_NUMBER: _ClassVar[int]
    INCLUDEVOTES_FIELD_NUMBER: _ClassVar[int]
    SHORT_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    INCLUDEFORSALEDATA_FIELD_NUMBER: _ClassVar[int]
    INCLUDEMETADATA_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    RETURN_PLAYTIME_STATS_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    STRIP_DESCRIPTION_BBCODE_FIELD_NUMBER: _ClassVar[int]
    DESIRED_REVISION_FIELD_NUMBER: _ClassVar[int]
    INCLUDEREACTIONS_FIELD_NUMBER: _ClassVar[int]
    publishedfileids: _containers.RepeatedScalarFieldContainer[int]
    includetags: bool
    includeadditionalpreviews: bool
    includechildren: bool
    includekvtags: bool
    includevotes: bool
    short_description: bool
    includeforsaledata: bool
    includemetadata: bool
    language: int
    return_playtime_stats: int
    appid: int
    strip_description_bbcode: bool
    desired_revision: EPublishedFileRevision
    includereactions: bool
    def __init__(self, publishedfileids: _Optional[_Iterable[int]] = ..., includetags: _Optional[bool] = ..., includeadditionalpreviews: _Optional[bool] = ..., includechildren: _Optional[bool] = ..., includekvtags: _Optional[bool] = ..., includevotes: _Optional[bool] = ..., short_description: _Optional[bool] = ..., includeforsaledata: _Optional[bool] = ..., includemetadata: _Optional[bool] = ..., language: _Optional[int] = ..., return_playtime_stats: _Optional[int] = ..., appid: _Optional[int] = ..., strip_description_bbcode: _Optional[bool] = ..., desired_revision: _Optional[_Union[EPublishedFileRevision, str]] = ..., includereactions: _Optional[bool] = ...) -> None: ...

class PublishedFileDetails(_message.Message):
    __slots__ = ("result", "publishedfileid", "creator", "creator_appid", "consumer_appid", "consumer_shortcutid", "filename", "file_size", "preview_file_size", "file_url", "preview_url", "youtubevideoid", "url", "hcontent_file", "hcontent_preview", "title", "file_description", "short_description", "time_created", "time_updated", "visibility", "flags", "workshop_file", "workshop_accepted", "show_subscribe_all", "num_comments_developer", "num_comments_public", "banned", "ban_reason", "banner", "can_be_deleted", "incompatible", "app_name", "file_type", "can_subscribe", "subscriptions", "favorited", "followers", "lifetime_subscriptions", "lifetime_favorited", "lifetime_followers", "lifetime_playtime", "lifetime_playtime_sessions", "views", "image_width", "image_height", "image_url", "spoiler_tag", "shortcutid", "shortcutname", "num_children", "num_reports", "previews", "tags", "children", "kvtags", "vote_data", "playtime_stats", "time_subscribed", "for_sale_data", "metadata", "language", "maybe_inappropriate_sex", "maybe_inappropriate_violence", "revision_change_number", "revision", "available_revisions", "reactions", "ban_text_check_result")
    class Tag(_message.Message):
        __slots__ = ("tag", "adminonly", "display_name")
        TAG_FIELD_NUMBER: _ClassVar[int]
        ADMINONLY_FIELD_NUMBER: _ClassVar[int]
        DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
        tag: str
        adminonly: bool
        display_name: str
        def __init__(self, tag: _Optional[str] = ..., adminonly: _Optional[bool] = ..., display_name: _Optional[str] = ...) -> None: ...
    class Preview(_message.Message):
        __slots__ = ("previewid", "sortorder", "url", "size", "filename", "youtubevideoid", "preview_type", "external_reference")
        PREVIEWID_FIELD_NUMBER: _ClassVar[int]
        SORTORDER_FIELD_NUMBER: _ClassVar[int]
        URL_FIELD_NUMBER: _ClassVar[int]
        SIZE_FIELD_NUMBER: _ClassVar[int]
        FILENAME_FIELD_NUMBER: _ClassVar[int]
        YOUTUBEVIDEOID_FIELD_NUMBER: _ClassVar[int]
        PREVIEW_TYPE_FIELD_NUMBER: _ClassVar[int]
        EXTERNAL_REFERENCE_FIELD_NUMBER: _ClassVar[int]
        previewid: int
        sortorder: int
        url: str
        size: int
        filename: str
        youtubevideoid: str
        preview_type: int
        external_reference: str
        def __init__(self, previewid: _Optional[int] = ..., sortorder: _Optional[int] = ..., url: _Optional[str] = ..., size: _Optional[int] = ..., filename: _Optional[str] = ..., youtubevideoid: _Optional[str] = ..., preview_type: _Optional[int] = ..., external_reference: _Optional[str] = ...) -> None: ...
    class Child(_message.Message):
        __slots__ = ("publishedfileid", "sortorder", "file_type")
        PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
        SORTORDER_FIELD_NUMBER: _ClassVar[int]
        FILE_TYPE_FIELD_NUMBER: _ClassVar[int]
        publishedfileid: int
        sortorder: int
        file_type: int
        def __init__(self, publishedfileid: _Optional[int] = ..., sortorder: _Optional[int] = ..., file_type: _Optional[int] = ...) -> None: ...
    class KVTag(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    class VoteData(_message.Message):
        __slots__ = ("score", "votes_up", "votes_down")
        SCORE_FIELD_NUMBER: _ClassVar[int]
        VOTES_UP_FIELD_NUMBER: _ClassVar[int]
        VOTES_DOWN_FIELD_NUMBER: _ClassVar[int]
        score: float
        votes_up: int
        votes_down: int
        def __init__(self, score: _Optional[float] = ..., votes_up: _Optional[int] = ..., votes_down: _Optional[int] = ...) -> None: ...
    class ForSaleData(_message.Message):
        __slots__ = ("is_for_sale", "price_category", "estatus", "price_category_floor", "price_is_pay_what_you_want", "discount_percentage")
        IS_FOR_SALE_FIELD_NUMBER: _ClassVar[int]
        PRICE_CATEGORY_FIELD_NUMBER: _ClassVar[int]
        ESTATUS_FIELD_NUMBER: _ClassVar[int]
        PRICE_CATEGORY_FLOOR_FIELD_NUMBER: _ClassVar[int]
        PRICE_IS_PAY_WHAT_YOU_WANT_FIELD_NUMBER: _ClassVar[int]
        DISCOUNT_PERCENTAGE_FIELD_NUMBER: _ClassVar[int]
        is_for_sale: bool
        price_category: int
        estatus: EPublishedFileForSaleStatus
        price_category_floor: int
        price_is_pay_what_you_want: bool
        discount_percentage: int
        def __init__(self, is_for_sale: _Optional[bool] = ..., price_category: _Optional[int] = ..., estatus: _Optional[_Union[EPublishedFileForSaleStatus, str]] = ..., price_category_floor: _Optional[int] = ..., price_is_pay_what_you_want: _Optional[bool] = ..., discount_percentage: _Optional[int] = ...) -> None: ...
    class PlaytimeStats(_message.Message):
        __slots__ = ("playtime_seconds", "num_sessions")
        PLAYTIME_SECONDS_FIELD_NUMBER: _ClassVar[int]
        NUM_SESSIONS_FIELD_NUMBER: _ClassVar[int]
        playtime_seconds: int
        num_sessions: int
        def __init__(self, playtime_seconds: _Optional[int] = ..., num_sessions: _Optional[int] = ...) -> None: ...
    class Reaction(_message.Message):
        __slots__ = ("reactionid", "count")
        REACTIONID_FIELD_NUMBER: _ClassVar[int]
        COUNT_FIELD_NUMBER: _ClassVar[int]
        reactionid: int
        count: int
        def __init__(self, reactionid: _Optional[int] = ..., count: _Optional[int] = ...) -> None: ...
    RESULT_FIELD_NUMBER: _ClassVar[int]
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    CREATOR_FIELD_NUMBER: _ClassVar[int]
    CREATOR_APPID_FIELD_NUMBER: _ClassVar[int]
    CONSUMER_APPID_FIELD_NUMBER: _ClassVar[int]
    CONSUMER_SHORTCUTID_FIELD_NUMBER: _ClassVar[int]
    FILENAME_FIELD_NUMBER: _ClassVar[int]
    FILE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_FILE_SIZE_FIELD_NUMBER: _ClassVar[int]
    FILE_URL_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_URL_FIELD_NUMBER: _ClassVar[int]
    YOUTUBEVIDEOID_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    HCONTENT_FILE_FIELD_NUMBER: _ClassVar[int]
    HCONTENT_PREVIEW_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    FILE_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    SHORT_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    TIME_CREATED_FIELD_NUMBER: _ClassVar[int]
    TIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
    VISIBILITY_FIELD_NUMBER: _ClassVar[int]
    FLAGS_FIELD_NUMBER: _ClassVar[int]
    WORKSHOP_FILE_FIELD_NUMBER: _ClassVar[int]
    WORKSHOP_ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    SHOW_SUBSCRIBE_ALL_FIELD_NUMBER: _ClassVar[int]
    NUM_COMMENTS_DEVELOPER_FIELD_NUMBER: _ClassVar[int]
    NUM_COMMENTS_PUBLIC_FIELD_NUMBER: _ClassVar[int]
    BANNED_FIELD_NUMBER: _ClassVar[int]
    BAN_REASON_FIELD_NUMBER: _ClassVar[int]
    BANNER_FIELD_NUMBER: _ClassVar[int]
    CAN_BE_DELETED_FIELD_NUMBER: _ClassVar[int]
    INCOMPATIBLE_FIELD_NUMBER: _ClassVar[int]
    APP_NAME_FIELD_NUMBER: _ClassVar[int]
    FILE_TYPE_FIELD_NUMBER: _ClassVar[int]
    CAN_SUBSCRIBE_FIELD_NUMBER: _ClassVar[int]
    SUBSCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    FAVORITED_FIELD_NUMBER: _ClassVar[int]
    FOLLOWERS_FIELD_NUMBER: _ClassVar[int]
    LIFETIME_SUBSCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    LIFETIME_FAVORITED_FIELD_NUMBER: _ClassVar[int]
    LIFETIME_FOLLOWERS_FIELD_NUMBER: _ClassVar[int]
    LIFETIME_PLAYTIME_FIELD_NUMBER: _ClassVar[int]
    LIFETIME_PLAYTIME_SESSIONS_FIELD_NUMBER: _ClassVar[int]
    VIEWS_FIELD_NUMBER: _ClassVar[int]
    IMAGE_WIDTH_FIELD_NUMBER: _ClassVar[int]
    IMAGE_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    IMAGE_URL_FIELD_NUMBER: _ClassVar[int]
    SPOILER_TAG_FIELD_NUMBER: _ClassVar[int]
    SHORTCUTID_FIELD_NUMBER: _ClassVar[int]
    SHORTCUTNAME_FIELD_NUMBER: _ClassVar[int]
    NUM_CHILDREN_FIELD_NUMBER: _ClassVar[int]
    NUM_REPORTS_FIELD_NUMBER: _ClassVar[int]
    PREVIEWS_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    CHILDREN_FIELD_NUMBER: _ClassVar[int]
    KVTAGS_FIELD_NUMBER: _ClassVar[int]
    VOTE_DATA_FIELD_NUMBER: _ClassVar[int]
    PLAYTIME_STATS_FIELD_NUMBER: _ClassVar[int]
    TIME_SUBSCRIBED_FIELD_NUMBER: _ClassVar[int]
    FOR_SALE_DATA_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    MAYBE_INAPPROPRIATE_SEX_FIELD_NUMBER: _ClassVar[int]
    MAYBE_INAPPROPRIATE_VIOLENCE_FIELD_NUMBER: _ClassVar[int]
    REVISION_CHANGE_NUMBER_FIELD_NUMBER: _ClassVar[int]
    REVISION_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_REVISIONS_FIELD_NUMBER: _ClassVar[int]
    REACTIONS_FIELD_NUMBER: _ClassVar[int]
    BAN_TEXT_CHECK_RESULT_FIELD_NUMBER: _ClassVar[int]
    result: int
    publishedfileid: int
    creator: int
    creator_appid: int
    consumer_appid: int
    consumer_shortcutid: int
    filename: str
    file_size: int
    preview_file_size: int
    file_url: str
    preview_url: str
    youtubevideoid: str
    url: str
    hcontent_file: int
    hcontent_preview: int
    title: str
    file_description: str
    short_description: str
    time_created: int
    time_updated: int
    visibility: int
    flags: int
    workshop_file: bool
    workshop_accepted: bool
    show_subscribe_all: bool
    num_comments_developer: int
    num_comments_public: int
    banned: bool
    ban_reason: str
    banner: int
    can_be_deleted: bool
    incompatible: bool
    app_name: str
    file_type: int
    can_subscribe: bool
    subscriptions: int
    favorited: int
    followers: int
    lifetime_subscriptions: int
    lifetime_favorited: int
    lifetime_followers: int
    lifetime_playtime: int
    lifetime_playtime_sessions: int
    views: int
    image_width: int
    image_height: int
    image_url: str
    spoiler_tag: bool
    shortcutid: int
    shortcutname: str
    num_children: int
    num_reports: int
    previews: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails.Preview]
    tags: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails.Tag]
    children: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails.Child]
    kvtags: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails.KVTag]
    vote_data: PublishedFileDetails.VoteData
    playtime_stats: PublishedFileDetails.PlaytimeStats
    time_subscribed: int
    for_sale_data: PublishedFileDetails.ForSaleData
    metadata: str
    language: int
    maybe_inappropriate_sex: bool
    maybe_inappropriate_violence: bool
    revision_change_number: int
    revision: EPublishedFileRevision
    available_revisions: _containers.RepeatedScalarFieldContainer[EPublishedFileRevision]
    reactions: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails.Reaction]
    ban_text_check_result: _steammessages_base_pb2.EBanContentCheckResult
    def __init__(self, result: _Optional[int] = ..., publishedfileid: _Optional[int] = ..., creator: _Optional[int] = ..., creator_appid: _Optional[int] = ..., consumer_appid: _Optional[int] = ..., consumer_shortcutid: _Optional[int] = ..., filename: _Optional[str] = ..., file_size: _Optional[int] = ..., preview_file_size: _Optional[int] = ..., file_url: _Optional[str] = ..., preview_url: _Optional[str] = ..., youtubevideoid: _Optional[str] = ..., url: _Optional[str] = ..., hcontent_file: _Optional[int] = ..., hcontent_preview: _Optional[int] = ..., title: _Optional[str] = ..., file_description: _Optional[str] = ..., short_description: _Optional[str] = ..., time_created: _Optional[int] = ..., time_updated: _Optional[int] = ..., visibility: _Optional[int] = ..., flags: _Optional[int] = ..., workshop_file: _Optional[bool] = ..., workshop_accepted: _Optional[bool] = ..., show_subscribe_all: _Optional[bool] = ..., num_comments_developer: _Optional[int] = ..., num_comments_public: _Optional[int] = ..., banned: _Optional[bool] = ..., ban_reason: _Optional[str] = ..., banner: _Optional[int] = ..., can_be_deleted: _Optional[bool] = ..., incompatible: _Optional[bool] = ..., app_name: _Optional[str] = ..., file_type: _Optional[int] = ..., can_subscribe: _Optional[bool] = ..., subscriptions: _Optional[int] = ..., favorited: _Optional[int] = ..., followers: _Optional[int] = ..., lifetime_subscriptions: _Optional[int] = ..., lifetime_favorited: _Optional[int] = ..., lifetime_followers: _Optional[int] = ..., lifetime_playtime: _Optional[int] = ..., lifetime_playtime_sessions: _Optional[int] = ..., views: _Optional[int] = ..., image_width: _Optional[int] = ..., image_height: _Optional[int] = ..., image_url: _Optional[str] = ..., spoiler_tag: _Optional[bool] = ..., shortcutid: _Optional[int] = ..., shortcutname: _Optional[str] = ..., num_children: _Optional[int] = ..., num_reports: _Optional[int] = ..., previews: _Optional[_Iterable[_Union[PublishedFileDetails.Preview, _Mapping]]] = ..., tags: _Optional[_Iterable[_Union[PublishedFileDetails.Tag, _Mapping]]] = ..., children: _Optional[_Iterable[_Union[PublishedFileDetails.Child, _Mapping]]] = ..., kvtags: _Optional[_Iterable[_Union[PublishedFileDetails.KVTag, _Mapping]]] = ..., vote_data: _Optional[_Union[PublishedFileDetails.VoteData, _Mapping]] = ..., playtime_stats: _Optional[_Union[PublishedFileDetails.PlaytimeStats, _Mapping]] = ..., time_subscribed: _Optional[int] = ..., for_sale_data: _Optional[_Union[PublishedFileDetails.ForSaleData, _Mapping]] = ..., metadata: _Optional[str] = ..., language: _Optional[int] = ..., maybe_inappropriate_sex: _Optional[bool] = ..., maybe_inappropriate_violence: _Optional[bool] = ..., revision_change_number: _Optional[int] = ..., revision: _Optional[_Union[EPublishedFileRevision, str]] = ..., available_revisions: _Optional[_Iterable[_Union[EPublishedFileRevision, str]]] = ..., reactions: _Optional[_Iterable[_Union[PublishedFileDetails.Reaction, _Mapping]]] = ..., ban_text_check_result: _Optional[_Union[_steammessages_base_pb2.EBanContentCheckResult, str]] = ...) -> None: ...

class CPublishedFile_GetDetails_Response(_message.Message):
    __slots__ = ("publishedfiledetails",)
    PUBLISHEDFILEDETAILS_FIELD_NUMBER: _ClassVar[int]
    publishedfiledetails: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails]
    def __init__(self, publishedfiledetails: _Optional[_Iterable[_Union[PublishedFileDetails, _Mapping]]] = ...) -> None: ...

class CPublishedFile_GetItemInfo_Request(_message.Message):
    __slots__ = ("appid", "last_time_updated", "workshop_items")
    class WorkshopItem(_message.Message):
        __slots__ = ("published_file_id", "time_updated", "desired_revision")
        PUBLISHED_FILE_ID_FIELD_NUMBER: _ClassVar[int]
        TIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
        DESIRED_REVISION_FIELD_NUMBER: _ClassVar[int]
        published_file_id: int
        time_updated: int
        desired_revision: EPublishedFileRevision
        def __init__(self, published_file_id: _Optional[int] = ..., time_updated: _Optional[int] = ..., desired_revision: _Optional[_Union[EPublishedFileRevision, str]] = ...) -> None: ...
    APPID_FIELD_NUMBER: _ClassVar[int]
    LAST_TIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
    WORKSHOP_ITEMS_FIELD_NUMBER: _ClassVar[int]
    appid: int
    last_time_updated: int
    workshop_items: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetItemInfo_Request.WorkshopItem]
    def __init__(self, appid: _Optional[int] = ..., last_time_updated: _Optional[int] = ..., workshop_items: _Optional[_Iterable[_Union[CPublishedFile_GetItemInfo_Request.WorkshopItem, _Mapping]]] = ...) -> None: ...

class CPublishedFile_GetItemInfo_Response(_message.Message):
    __slots__ = ("update_time", "workshop_items", "private_items")
    class WorkshopItemInfo(_message.Message):
        __slots__ = ("published_file_id", "time_updated", "manifest_id", "flags")
        PUBLISHED_FILE_ID_FIELD_NUMBER: _ClassVar[int]
        TIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
        MANIFEST_ID_FIELD_NUMBER: _ClassVar[int]
        FLAGS_FIELD_NUMBER: _ClassVar[int]
        published_file_id: int
        time_updated: int
        manifest_id: int
        flags: int
        def __init__(self, published_file_id: _Optional[int] = ..., time_updated: _Optional[int] = ..., manifest_id: _Optional[int] = ..., flags: _Optional[int] = ...) -> None: ...
    UPDATE_TIME_FIELD_NUMBER: _ClassVar[int]
    WORKSHOP_ITEMS_FIELD_NUMBER: _ClassVar[int]
    PRIVATE_ITEMS_FIELD_NUMBER: _ClassVar[int]
    update_time: int
    workshop_items: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetItemInfo_Response.WorkshopItemInfo]
    private_items: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, update_time: _Optional[int] = ..., workshop_items: _Optional[_Iterable[_Union[CPublishedFile_GetItemInfo_Response.WorkshopItemInfo, _Mapping]]] = ..., private_items: _Optional[_Iterable[int]] = ...) -> None: ...

class CPublishedFile_GetUserFiles_Request(_message.Message):
    __slots__ = ("steamid", "appid", "page", "numperpage", "type", "sortmethod", "privacy", "requiredtags", "excludedtags", "required_kv_tags", "filetype", "creator_appid", "match_cloud_filename", "cache_max_age_seconds", "language", "taggroups", "totalonly", "ids_only", "return_vote_data", "return_tags", "return_kv_tags", "return_previews", "return_children", "return_short_description", "return_for_sale_data", "return_metadata", "return_playtime_stats", "strip_description_bbcode", "return_reactions", "startindex_override", "desired_revision", "return_apps")
    class KVTag(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    class TagGroup(_message.Message):
        __slots__ = ("tags",)
        TAGS_FIELD_NUMBER: _ClassVar[int]
        tags: _containers.RepeatedScalarFieldContainer[str]
        def __init__(self, tags: _Optional[_Iterable[str]] = ...) -> None: ...
    STEAMID_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    NUMPERPAGE_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SORTMETHOD_FIELD_NUMBER: _ClassVar[int]
    PRIVACY_FIELD_NUMBER: _ClassVar[int]
    REQUIREDTAGS_FIELD_NUMBER: _ClassVar[int]
    EXCLUDEDTAGS_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_KV_TAGS_FIELD_NUMBER: _ClassVar[int]
    FILETYPE_FIELD_NUMBER: _ClassVar[int]
    CREATOR_APPID_FIELD_NUMBER: _ClassVar[int]
    MATCH_CLOUD_FILENAME_FIELD_NUMBER: _ClassVar[int]
    CACHE_MAX_AGE_SECONDS_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    TAGGROUPS_FIELD_NUMBER: _ClassVar[int]
    TOTALONLY_FIELD_NUMBER: _ClassVar[int]
    IDS_ONLY_FIELD_NUMBER: _ClassVar[int]
    RETURN_VOTE_DATA_FIELD_NUMBER: _ClassVar[int]
    RETURN_TAGS_FIELD_NUMBER: _ClassVar[int]
    RETURN_KV_TAGS_FIELD_NUMBER: _ClassVar[int]
    RETURN_PREVIEWS_FIELD_NUMBER: _ClassVar[int]
    RETURN_CHILDREN_FIELD_NUMBER: _ClassVar[int]
    RETURN_SHORT_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    RETURN_FOR_SALE_DATA_FIELD_NUMBER: _ClassVar[int]
    RETURN_METADATA_FIELD_NUMBER: _ClassVar[int]
    RETURN_PLAYTIME_STATS_FIELD_NUMBER: _ClassVar[int]
    STRIP_DESCRIPTION_BBCODE_FIELD_NUMBER: _ClassVar[int]
    RETURN_REACTIONS_FIELD_NUMBER: _ClassVar[int]
    STARTINDEX_OVERRIDE_FIELD_NUMBER: _ClassVar[int]
    DESIRED_REVISION_FIELD_NUMBER: _ClassVar[int]
    RETURN_APPS_FIELD_NUMBER: _ClassVar[int]
    steamid: int
    appid: int
    page: int
    numperpage: int
    type: str
    sortmethod: str
    privacy: int
    requiredtags: _containers.RepeatedScalarFieldContainer[str]
    excludedtags: _containers.RepeatedScalarFieldContainer[str]
    required_kv_tags: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetUserFiles_Request.KVTag]
    filetype: int
    creator_appid: int
    match_cloud_filename: str
    cache_max_age_seconds: int
    language: int
    taggroups: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetUserFiles_Request.TagGroup]
    totalonly: bool
    ids_only: bool
    return_vote_data: bool
    return_tags: bool
    return_kv_tags: bool
    return_previews: bool
    return_children: bool
    return_short_description: bool
    return_for_sale_data: bool
    return_metadata: bool
    return_playtime_stats: int
    strip_description_bbcode: bool
    return_reactions: bool
    startindex_override: int
    desired_revision: EPublishedFileRevision
    return_apps: bool
    def __init__(self, steamid: _Optional[int] = ..., appid: _Optional[int] = ..., page: _Optional[int] = ..., numperpage: _Optional[int] = ..., type: _Optional[str] = ..., sortmethod: _Optional[str] = ..., privacy: _Optional[int] = ..., requiredtags: _Optional[_Iterable[str]] = ..., excludedtags: _Optional[_Iterable[str]] = ..., required_kv_tags: _Optional[_Iterable[_Union[CPublishedFile_GetUserFiles_Request.KVTag, _Mapping]]] = ..., filetype: _Optional[int] = ..., creator_appid: _Optional[int] = ..., match_cloud_filename: _Optional[str] = ..., cache_max_age_seconds: _Optional[int] = ..., language: _Optional[int] = ..., taggroups: _Optional[_Iterable[_Union[CPublishedFile_GetUserFiles_Request.TagGroup, _Mapping]]] = ..., totalonly: _Optional[bool] = ..., ids_only: _Optional[bool] = ..., return_vote_data: _Optional[bool] = ..., return_tags: _Optional[bool] = ..., return_kv_tags: _Optional[bool] = ..., return_previews: _Optional[bool] = ..., return_children: _Optional[bool] = ..., return_short_description: _Optional[bool] = ..., return_for_sale_data: _Optional[bool] = ..., return_metadata: _Optional[bool] = ..., return_playtime_stats: _Optional[int] = ..., strip_description_bbcode: _Optional[bool] = ..., return_reactions: _Optional[bool] = ..., startindex_override: _Optional[int] = ..., desired_revision: _Optional[_Union[EPublishedFileRevision, str]] = ..., return_apps: _Optional[bool] = ...) -> None: ...

class CPublishedFile_GetUserFiles_Response(_message.Message):
    __slots__ = ("total", "startindex", "publishedfiledetails", "apps")
    class App(_message.Message):
        __slots__ = ("appid", "name", "shortcutid", "private")
        APPID_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        SHORTCUTID_FIELD_NUMBER: _ClassVar[int]
        PRIVATE_FIELD_NUMBER: _ClassVar[int]
        appid: int
        name: str
        shortcutid: int
        private: bool
        def __init__(self, appid: _Optional[int] = ..., name: _Optional[str] = ..., shortcutid: _Optional[int] = ..., private: _Optional[bool] = ...) -> None: ...
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    STARTINDEX_FIELD_NUMBER: _ClassVar[int]
    PUBLISHEDFILEDETAILS_FIELD_NUMBER: _ClassVar[int]
    APPS_FIELD_NUMBER: _ClassVar[int]
    total: int
    startindex: int
    publishedfiledetails: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails]
    apps: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetUserFiles_Response.App]
    def __init__(self, total: _Optional[int] = ..., startindex: _Optional[int] = ..., publishedfiledetails: _Optional[_Iterable[_Union[PublishedFileDetails, _Mapping]]] = ..., apps: _Optional[_Iterable[_Union[CPublishedFile_GetUserFiles_Response.App, _Mapping]]] = ...) -> None: ...

class CPublishedFile_AreFilesInSubscriptionList_Request(_message.Message):
    __slots__ = ("appid", "publishedfileids", "listtype", "filetype", "workshopfiletype")
    APPID_FIELD_NUMBER: _ClassVar[int]
    PUBLISHEDFILEIDS_FIELD_NUMBER: _ClassVar[int]
    LISTTYPE_FIELD_NUMBER: _ClassVar[int]
    FILETYPE_FIELD_NUMBER: _ClassVar[int]
    WORKSHOPFILETYPE_FIELD_NUMBER: _ClassVar[int]
    appid: int
    publishedfileids: _containers.RepeatedScalarFieldContainer[int]
    listtype: int
    filetype: int
    workshopfiletype: int
    def __init__(self, appid: _Optional[int] = ..., publishedfileids: _Optional[_Iterable[int]] = ..., listtype: _Optional[int] = ..., filetype: _Optional[int] = ..., workshopfiletype: _Optional[int] = ...) -> None: ...

class CPublishedFile_AreFilesInSubscriptionList_Response(_message.Message):
    __slots__ = ("files",)
    class InList(_message.Message):
        __slots__ = ("publishedfileid", "inlist")
        PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
        INLIST_FIELD_NUMBER: _ClassVar[int]
        publishedfileid: int
        inlist: bool
        def __init__(self, publishedfileid: _Optional[int] = ..., inlist: _Optional[bool] = ...) -> None: ...
    FILES_FIELD_NUMBER: _ClassVar[int]
    files: _containers.RepeatedCompositeFieldContainer[CPublishedFile_AreFilesInSubscriptionList_Response.InList]
    def __init__(self, files: _Optional[_Iterable[_Union[CPublishedFile_AreFilesInSubscriptionList_Response.InList, _Mapping]]] = ...) -> None: ...

class CPublishedFile_Update_Request(_message.Message):
    __slots__ = ("appid", "publishedfileid", "title", "file_description", "visibility", "tags", "filename", "preview_filename", "spoiler_tag", "image_width", "image_height")
    APPID_FIELD_NUMBER: _ClassVar[int]
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    FILE_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    VISIBILITY_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    FILENAME_FIELD_NUMBER: _ClassVar[int]
    PREVIEW_FILENAME_FIELD_NUMBER: _ClassVar[int]
    SPOILER_TAG_FIELD_NUMBER: _ClassVar[int]
    IMAGE_WIDTH_FIELD_NUMBER: _ClassVar[int]
    IMAGE_HEIGHT_FIELD_NUMBER: _ClassVar[int]
    appid: int
    publishedfileid: int
    title: str
    file_description: str
    visibility: int
    tags: _containers.RepeatedScalarFieldContainer[str]
    filename: str
    preview_filename: str
    spoiler_tag: bool
    image_width: int
    image_height: int
    def __init__(self, appid: _Optional[int] = ..., publishedfileid: _Optional[int] = ..., title: _Optional[str] = ..., file_description: _Optional[str] = ..., visibility: _Optional[int] = ..., tags: _Optional[_Iterable[str]] = ..., filename: _Optional[str] = ..., preview_filename: _Optional[str] = ..., spoiler_tag: _Optional[bool] = ..., image_width: _Optional[int] = ..., image_height: _Optional[int] = ...) -> None: ...

class CPublishedFile_Update_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_Delete_Request(_message.Message):
    __slots__ = ("publishedfileid",)
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    def __init__(self, publishedfileid: _Optional[int] = ...) -> None: ...

class CPublishedFile_Delete_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_GetChangeHistoryEntry_Request(_message.Message):
    __slots__ = ("publishedfileid", "timestamp", "language")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    timestamp: int
    language: int
    def __init__(self, publishedfileid: _Optional[int] = ..., timestamp: _Optional[int] = ..., language: _Optional[int] = ...) -> None: ...

class CPublishedFile_GetChangeHistoryEntry_Response(_message.Message):
    __slots__ = ("change_description", "language")
    CHANGE_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    change_description: str
    language: int
    def __init__(self, change_description: _Optional[str] = ..., language: _Optional[int] = ...) -> None: ...

class CPublishedFile_GetChangeHistory_Request(_message.Message):
    __slots__ = ("publishedfileid", "total_only", "startindex", "count", "language")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    TOTAL_ONLY_FIELD_NUMBER: _ClassVar[int]
    STARTINDEX_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    total_only: bool
    startindex: int
    count: int
    language: int
    def __init__(self, publishedfileid: _Optional[int] = ..., total_only: _Optional[bool] = ..., startindex: _Optional[int] = ..., count: _Optional[int] = ..., language: _Optional[int] = ...) -> None: ...

class CPublishedFile_GetChangeHistory_Response(_message.Message):
    __slots__ = ("changes", "total")
    class ChangeLog(_message.Message):
        __slots__ = ("timestamp", "change_description", "language")
        TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
        CHANGE_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
        LANGUAGE_FIELD_NUMBER: _ClassVar[int]
        timestamp: int
        change_description: str
        language: int
        def __init__(self, timestamp: _Optional[int] = ..., change_description: _Optional[str] = ..., language: _Optional[int] = ...) -> None: ...
    CHANGES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    changes: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetChangeHistory_Response.ChangeLog]
    total: int
    def __init__(self, changes: _Optional[_Iterable[_Union[CPublishedFile_GetChangeHistory_Response.ChangeLog, _Mapping]]] = ..., total: _Optional[int] = ...) -> None: ...

class CPublishedFile_RefreshVotingQueue_Request(_message.Message):
    __slots__ = ("appid", "matching_file_type", "tags", "match_all_tags", "excluded_tags", "desired_queue_size", "desired_revision")
    APPID_FIELD_NUMBER: _ClassVar[int]
    MATCHING_FILE_TYPE_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    MATCH_ALL_TAGS_FIELD_NUMBER: _ClassVar[int]
    EXCLUDED_TAGS_FIELD_NUMBER: _ClassVar[int]
    DESIRED_QUEUE_SIZE_FIELD_NUMBER: _ClassVar[int]
    DESIRED_REVISION_FIELD_NUMBER: _ClassVar[int]
    appid: int
    matching_file_type: int
    tags: _containers.RepeatedScalarFieldContainer[str]
    match_all_tags: bool
    excluded_tags: _containers.RepeatedScalarFieldContainer[str]
    desired_queue_size: int
    desired_revision: EPublishedFileRevision
    def __init__(self, appid: _Optional[int] = ..., matching_file_type: _Optional[int] = ..., tags: _Optional[_Iterable[str]] = ..., match_all_tags: _Optional[bool] = ..., excluded_tags: _Optional[_Iterable[str]] = ..., desired_queue_size: _Optional[int] = ..., desired_revision: _Optional[_Union[EPublishedFileRevision, str]] = ...) -> None: ...

class CPublishedFile_RefreshVotingQueue_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_QueryFiles_Request(_message.Message):
    __slots__ = ("query_type", "page", "cursor", "numperpage", "creator_appid", "appid", "requiredtags", "excludedtags", "match_all_tags", "required_flags", "omitted_flags", "search_text", "filetype", "child_publishedfileid", "days", "include_recent_votes_only", "cache_max_age_seconds", "language", "required_kv_tags", "taggroups", "date_range_created", "date_range_updated", "totalonly", "ids_only", "return_vote_data", "return_tags", "return_kv_tags", "return_previews", "return_children", "return_short_description", "return_for_sale_data", "return_metadata", "return_playtime_stats", "return_details", "strip_description_bbcode", "desired_revision", "return_reactions")
    class KVTag(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    class TagGroup(_message.Message):
        __slots__ = ("tags",)
        TAGS_FIELD_NUMBER: _ClassVar[int]
        tags: _containers.RepeatedScalarFieldContainer[str]
        def __init__(self, tags: _Optional[_Iterable[str]] = ...) -> None: ...
    class DateRange(_message.Message):
        __slots__ = ("timestamp_start", "timestamp_end")
        TIMESTAMP_START_FIELD_NUMBER: _ClassVar[int]
        TIMESTAMP_END_FIELD_NUMBER: _ClassVar[int]
        timestamp_start: int
        timestamp_end: int
        def __init__(self, timestamp_start: _Optional[int] = ..., timestamp_end: _Optional[int] = ...) -> None: ...
    QUERY_TYPE_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    CURSOR_FIELD_NUMBER: _ClassVar[int]
    NUMPERPAGE_FIELD_NUMBER: _ClassVar[int]
    CREATOR_APPID_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    REQUIREDTAGS_FIELD_NUMBER: _ClassVar[int]
    EXCLUDEDTAGS_FIELD_NUMBER: _ClassVar[int]
    MATCH_ALL_TAGS_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_FLAGS_FIELD_NUMBER: _ClassVar[int]
    OMITTED_FLAGS_FIELD_NUMBER: _ClassVar[int]
    SEARCH_TEXT_FIELD_NUMBER: _ClassVar[int]
    FILETYPE_FIELD_NUMBER: _ClassVar[int]
    CHILD_PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    DAYS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_RECENT_VOTES_ONLY_FIELD_NUMBER: _ClassVar[int]
    CACHE_MAX_AGE_SECONDS_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_KV_TAGS_FIELD_NUMBER: _ClassVar[int]
    TAGGROUPS_FIELD_NUMBER: _ClassVar[int]
    DATE_RANGE_CREATED_FIELD_NUMBER: _ClassVar[int]
    DATE_RANGE_UPDATED_FIELD_NUMBER: _ClassVar[int]
    TOTALONLY_FIELD_NUMBER: _ClassVar[int]
    IDS_ONLY_FIELD_NUMBER: _ClassVar[int]
    RETURN_VOTE_DATA_FIELD_NUMBER: _ClassVar[int]
    RETURN_TAGS_FIELD_NUMBER: _ClassVar[int]
    RETURN_KV_TAGS_FIELD_NUMBER: _ClassVar[int]
    RETURN_PREVIEWS_FIELD_NUMBER: _ClassVar[int]
    RETURN_CHILDREN_FIELD_NUMBER: _ClassVar[int]
    RETURN_SHORT_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    RETURN_FOR_SALE_DATA_FIELD_NUMBER: _ClassVar[int]
    RETURN_METADATA_FIELD_NUMBER: _ClassVar[int]
    RETURN_PLAYTIME_STATS_FIELD_NUMBER: _ClassVar[int]
    RETURN_DETAILS_FIELD_NUMBER: _ClassVar[int]
    STRIP_DESCRIPTION_BBCODE_FIELD_NUMBER: _ClassVar[int]
    DESIRED_REVISION_FIELD_NUMBER: _ClassVar[int]
    RETURN_REACTIONS_FIELD_NUMBER: _ClassVar[int]
    query_type: int
    page: int
    cursor: str
    numperpage: int
    creator_appid: int
    appid: int
    requiredtags: _containers.RepeatedScalarFieldContainer[str]
    excludedtags: _containers.RepeatedScalarFieldContainer[str]
    match_all_tags: bool
    required_flags: _containers.RepeatedScalarFieldContainer[str]
    omitted_flags: _containers.RepeatedScalarFieldContainer[str]
    search_text: str
    filetype: int
    child_publishedfileid: int
    days: int
    include_recent_votes_only: bool
    cache_max_age_seconds: int
    language: int
    required_kv_tags: _containers.RepeatedCompositeFieldContainer[CPublishedFile_QueryFiles_Request.KVTag]
    taggroups: _containers.RepeatedCompositeFieldContainer[CPublishedFile_QueryFiles_Request.TagGroup]
    date_range_created: CPublishedFile_QueryFiles_Request.DateRange
    date_range_updated: CPublishedFile_QueryFiles_Request.DateRange
    totalonly: bool
    ids_only: bool
    return_vote_data: bool
    return_tags: bool
    return_kv_tags: bool
    return_previews: bool
    return_children: bool
    return_short_description: bool
    return_for_sale_data: bool
    return_metadata: bool
    return_playtime_stats: int
    return_details: bool
    strip_description_bbcode: bool
    desired_revision: EPublishedFileRevision
    return_reactions: bool
    def __init__(self, query_type: _Optional[int] = ..., page: _Optional[int] = ..., cursor: _Optional[str] = ..., numperpage: _Optional[int] = ..., creator_appid: _Optional[int] = ..., appid: _Optional[int] = ..., requiredtags: _Optional[_Iterable[str]] = ..., excludedtags: _Optional[_Iterable[str]] = ..., match_all_tags: _Optional[bool] = ..., required_flags: _Optional[_Iterable[str]] = ..., omitted_flags: _Optional[_Iterable[str]] = ..., search_text: _Optional[str] = ..., filetype: _Optional[int] = ..., child_publishedfileid: _Optional[int] = ..., days: _Optional[int] = ..., include_recent_votes_only: _Optional[bool] = ..., cache_max_age_seconds: _Optional[int] = ..., language: _Optional[int] = ..., required_kv_tags: _Optional[_Iterable[_Union[CPublishedFile_QueryFiles_Request.KVTag, _Mapping]]] = ..., taggroups: _Optional[_Iterable[_Union[CPublishedFile_QueryFiles_Request.TagGroup, _Mapping]]] = ..., date_range_created: _Optional[_Union[CPublishedFile_QueryFiles_Request.DateRange, _Mapping]] = ..., date_range_updated: _Optional[_Union[CPublishedFile_QueryFiles_Request.DateRange, _Mapping]] = ..., totalonly: _Optional[bool] = ..., ids_only: _Optional[bool] = ..., return_vote_data: _Optional[bool] = ..., return_tags: _Optional[bool] = ..., return_kv_tags: _Optional[bool] = ..., return_previews: _Optional[bool] = ..., return_children: _Optional[bool] = ..., return_short_description: _Optional[bool] = ..., return_for_sale_data: _Optional[bool] = ..., return_metadata: _Optional[bool] = ..., return_playtime_stats: _Optional[int] = ..., return_details: _Optional[bool] = ..., strip_description_bbcode: _Optional[bool] = ..., desired_revision: _Optional[_Union[EPublishedFileRevision, str]] = ..., return_reactions: _Optional[bool] = ...) -> None: ...

class CPublishedFile_QueryFiles_Response(_message.Message):
    __slots__ = ("total", "publishedfiledetails", "next_cursor")
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    PUBLISHEDFILEDETAILS_FIELD_NUMBER: _ClassVar[int]
    NEXT_CURSOR_FIELD_NUMBER: _ClassVar[int]
    total: int
    publishedfiledetails: _containers.RepeatedCompositeFieldContainer[PublishedFileDetails]
    next_cursor: str
    def __init__(self, total: _Optional[int] = ..., publishedfiledetails: _Optional[_Iterable[_Union[PublishedFileDetails, _Mapping]]] = ..., next_cursor: _Optional[str] = ...) -> None: ...

class CPublishedFile_AddAppRelationship_Request(_message.Message):
    __slots__ = ("publishedfileid", "appid", "relationship")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    RELATIONSHIP_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    appid: int
    relationship: int
    def __init__(self, publishedfileid: _Optional[int] = ..., appid: _Optional[int] = ..., relationship: _Optional[int] = ...) -> None: ...

class CPublishedFile_AddAppRelationship_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_RemoveAppRelationship_Request(_message.Message):
    __slots__ = ("publishedfileid", "appid", "relationship")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    APPID_FIELD_NUMBER: _ClassVar[int]
    RELATIONSHIP_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    appid: int
    relationship: int
    def __init__(self, publishedfileid: _Optional[int] = ..., appid: _Optional[int] = ..., relationship: _Optional[int] = ...) -> None: ...

class CPublishedFile_RemoveAppRelationship_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_GetAppRelationships_Request(_message.Message):
    __slots__ = ("publishedfileid",)
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    def __init__(self, publishedfileid: _Optional[int] = ...) -> None: ...

class CPublishedFile_GetAppRelationships_Response(_message.Message):
    __slots__ = ("app_relationships",)
    class AppRelationship(_message.Message):
        __slots__ = ("appid", "relationship")
        APPID_FIELD_NUMBER: _ClassVar[int]
        RELATIONSHIP_FIELD_NUMBER: _ClassVar[int]
        appid: int
        relationship: int
        def __init__(self, appid: _Optional[int] = ..., relationship: _Optional[int] = ...) -> None: ...
    APP_RELATIONSHIPS_FIELD_NUMBER: _ClassVar[int]
    app_relationships: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetAppRelationships_Response.AppRelationship]
    def __init__(self, app_relationships: _Optional[_Iterable[_Union[CPublishedFile_GetAppRelationships_Response.AppRelationship, _Mapping]]] = ...) -> None: ...

class CPublishedFile_StartPlaytimeTracking_Request(_message.Message):
    __slots__ = ("appid", "publishedfileids")
    APPID_FIELD_NUMBER: _ClassVar[int]
    PUBLISHEDFILEIDS_FIELD_NUMBER: _ClassVar[int]
    appid: int
    publishedfileids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, appid: _Optional[int] = ..., publishedfileids: _Optional[_Iterable[int]] = ...) -> None: ...

class CPublishedFile_StartPlaytimeTracking_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_StopPlaytimeTracking_Request(_message.Message):
    __slots__ = ("appid", "publishedfileids")
    APPID_FIELD_NUMBER: _ClassVar[int]
    PUBLISHEDFILEIDS_FIELD_NUMBER: _ClassVar[int]
    appid: int
    publishedfileids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, appid: _Optional[int] = ..., publishedfileids: _Optional[_Iterable[int]] = ...) -> None: ...

class CPublishedFile_StopPlaytimeTracking_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_StopPlaytimeTrackingForAllAppItems_Request(_message.Message):
    __slots__ = ("appid",)
    APPID_FIELD_NUMBER: _ClassVar[int]
    appid: int
    def __init__(self, appid: _Optional[int] = ...) -> None: ...

class CPublishedFile_StopPlaytimeTrackingForAllAppItems_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_SetPlaytimeForControllerConfigs_Request(_message.Message):
    __slots__ = ("appid", "controller_config_usage")
    class ControllerConfigUsage(_message.Message):
        __slots__ = ("publishedfileid", "seconds_active")
        PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
        SECONDS_ACTIVE_FIELD_NUMBER: _ClassVar[int]
        publishedfileid: int
        seconds_active: float
        def __init__(self, publishedfileid: _Optional[int] = ..., seconds_active: _Optional[float] = ...) -> None: ...
    APPID_FIELD_NUMBER: _ClassVar[int]
    CONTROLLER_CONFIG_USAGE_FIELD_NUMBER: _ClassVar[int]
    appid: int
    controller_config_usage: _containers.RepeatedCompositeFieldContainer[CPublishedFile_SetPlaytimeForControllerConfigs_Request.ControllerConfigUsage]
    def __init__(self, appid: _Optional[int] = ..., controller_config_usage: _Optional[_Iterable[_Union[CPublishedFile_SetPlaytimeForControllerConfigs_Request.ControllerConfigUsage, _Mapping]]] = ...) -> None: ...

class CPublishedFile_SetPlaytimeForControllerConfigs_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_AddChild_Request(_message.Message):
    __slots__ = ("publishedfileid", "child_publishedfileid")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    CHILD_PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    child_publishedfileid: int
    def __init__(self, publishedfileid: _Optional[int] = ..., child_publishedfileid: _Optional[int] = ...) -> None: ...

class CPublishedFile_AddChild_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_RemoveChild_Request(_message.Message):
    __slots__ = ("publishedfileid", "child_publishedfileid")
    PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    CHILD_PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
    publishedfileid: int
    child_publishedfileid: int
    def __init__(self, publishedfileid: _Optional[int] = ..., child_publishedfileid: _Optional[int] = ...) -> None: ...

class CPublishedFile_RemoveChild_Response(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CPublishedFile_GetUserVoteSummary_Request(_message.Message):
    __slots__ = ("publishedfileids",)
    PUBLISHEDFILEIDS_FIELD_NUMBER: _ClassVar[int]
    publishedfileids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, publishedfileids: _Optional[_Iterable[int]] = ...) -> None: ...

class CPublishedFile_GetUserVoteSummary_Response(_message.Message):
    __slots__ = ("summaries",)
    class VoteSummary(_message.Message):
        __slots__ = ("publishedfileid", "vote_for", "vote_against", "reported")
        PUBLISHEDFILEID_FIELD_NUMBER: _ClassVar[int]
        VOTE_FOR_FIELD_NUMBER: _ClassVar[int]
        VOTE_AGAINST_FIELD_NUMBER: _ClassVar[int]
        REPORTED_FIELD_NUMBER: _ClassVar[int]
        publishedfileid: int
        vote_for: bool
        vote_against: bool
        reported: bool
        def __init__(self, publishedfileid: _Optional[int] = ..., vote_for: _Optional[bool] = ..., vote_against: _Optional[bool] = ..., reported: _Optional[bool] = ...) -> None: ...
    SUMMARIES_FIELD_NUMBER: _ClassVar[int]
    summaries: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetUserVoteSummary_Response.VoteSummary]
    def __init__(self, summaries: _Optional[_Iterable[_Union[CPublishedFile_GetUserVoteSummary_Response.VoteSummary, _Mapping]]] = ...) -> None: ...

class CPublishedFile_GetItemChanges_Request(_message.Message):
    __slots__ = ("appid", "last_time_updated", "num_items_max")
    APPID_FIELD_NUMBER: _ClassVar[int]
    LAST_TIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
    NUM_ITEMS_MAX_FIELD_NUMBER: _ClassVar[int]
    appid: int
    last_time_updated: int
    num_items_max: int
    def __init__(self, appid: _Optional[int] = ..., last_time_updated: _Optional[int] = ..., num_items_max: _Optional[int] = ...) -> None: ...

class CPublishedFile_GetItemChanges_Response(_message.Message):
    __slots__ = ("update_time", "workshop_items")
    class WorkshopItemInfo(_message.Message):
        __slots__ = ("published_file_id", "time_updated", "manifest_id")
        PUBLISHED_FILE_ID_FIELD_NUMBER: _ClassVar[int]
        TIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
        MANIFEST_ID_FIELD_NUMBER: _ClassVar[int]
        published_file_id: int
        time_updated: int
        manifest_id: int
        def __init__(self, published_file_id: _Optional[int] = ..., time_updated: _Optional[int] = ..., manifest_id: _Optional[int] = ...) -> None: ...
    UPDATE_TIME_FIELD_NUMBER: _ClassVar[int]
    WORKSHOP_ITEMS_FIELD_NUMBER: _ClassVar[int]
    update_time: int
    workshop_items: _containers.RepeatedCompositeFieldContainer[CPublishedFile_GetItemChanges_Response.WorkshopItemInfo]
    def __init__(self, update_time: _Optional[int] = ..., workshop_items: _Optional[_Iterable[_Union[CPublishedFile_GetItemChanges_Response.WorkshopItemInfo, _Mapping]]] = ...) -> None: ...

class CPublishedFile_FileSubscribed_Notification(_message.Message):
    __slots__ = ("published_file_id", "app_id", "file_hcontent", "file_size", "rtime_subscribed", "is_depot_content", "rtime_updated", "revisions")
    class RevisionData(_message.Message):
        __slots__ = ("revision", "file_hcontent", "rtime_updated")
        REVISION_FIELD_NUMBER: _ClassVar[int]
        FILE_HCONTENT_FIELD_NUMBER: _ClassVar[int]
        RTIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
        revision: EPublishedFileRevision
        file_hcontent: int
        rtime_updated: int
        def __init__(self, revision: _Optional[_Union[EPublishedFileRevision, str]] = ..., file_hcontent: _Optional[int] = ..., rtime_updated: _Optional[int] = ...) -> None: ...
    PUBLISHED_FILE_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    FILE_HCONTENT_FIELD_NUMBER: _ClassVar[int]
    FILE_SIZE_FIELD_NUMBER: _ClassVar[int]
    RTIME_SUBSCRIBED_FIELD_NUMBER: _ClassVar[int]
    IS_DEPOT_CONTENT_FIELD_NUMBER: _ClassVar[int]
    RTIME_UPDATED_FIELD_NUMBER: _ClassVar[int]
    REVISIONS_FIELD_NUMBER: _ClassVar[int]
    published_file_id: int
    app_id: int
    file_hcontent: int
    file_size: int
    rtime_subscribed: int
    is_depot_content: bool
    rtime_updated: int
    revisions: _containers.RepeatedCompositeFieldContainer[CPublishedFile_FileSubscribed_Notification.RevisionData]
    def __init__(self, published_file_id: _Optional[int] = ..., app_id: _Optional[int] = ..., file_hcontent: _Optional[int] = ..., file_size: _Optional[int] = ..., rtime_subscribed: _Optional[int] = ..., is_depot_content: _Optional[bool] = ..., rtime_updated: _Optional[int] = ..., revisions: _Optional[_Iterable[_Union[CPublishedFile_FileSubscribed_Notification.RevisionData, _Mapping]]] = ...) -> None: ...

class CPublishedFile_FileUnsubscribed_Notification(_message.Message):
    __slots__ = ("published_file_id", "app_id")
    PUBLISHED_FILE_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    published_file_id: int
    app_id: int
    def __init__(self, published_file_id: _Optional[int] = ..., app_id: _Optional[int] = ...) -> None: ...

class CPublishedFile_FileDeleted_Client_Notification(_message.Message):
    __slots__ = ("published_file_id", "app_id")
    PUBLISHED_FILE_ID_FIELD_NUMBER: _ClassVar[int]
    APP_ID_FIELD_NUMBER: _ClassVar[int]
    published_file_id: int
    app_id: int
    def __init__(self, published_file_id: _Optional[int] = ..., app_id: _Optional[int] = ...) -> None: ...

class PublishedFile(_service.service): ...

class PublishedFile_Stub(PublishedFile): ...

class PublishedFileClient(_service.service): ...

class PublishedFileClient_Stub(PublishedFileClient): ...
