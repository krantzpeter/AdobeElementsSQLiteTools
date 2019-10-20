import sqlite3 as lite
import ntpath
import csv
import time
import sys
import ctypes
import datetime
from PyQt5.QtGui import QImage

if sys.version_info[0] < 3:
    import pyexiv2

debug_mode = True


def CreateTag(db_con, tag_name, parent_tag_id, can_have_children=0):
    # dbl_auto_id_table.last_assigned_id
    '''
    Adds a tag under this parent.  Also updates the parent tag in tag_table to ensure can_have_children is set.
    :param db_con:              Connection to open database
    :param tag_name:            Name of tag to insert
    :param parent_tag_id:       The tag id of the parent tag under which this new tag should sit
    :param can_have_children    Indicate whether the tag should be set to allow children tags (dfault = 0 for false; 1 = true)
    :return:
    '''

    with db_con:

        cur = db_con.cursor()

        # Ensure parent has can_have_children field set as we're about to add a child
        query = """
             UPDATE tag_table
             SET 
                 can_have_children = 1
             WHERE
                 id = ?;            
         """
        cur = db_con.cursor()
        cur.execute(query, (str(parent_tag_id),))

        # Get last_assigned_id
        cur.execute("""
        SELECT last_assigned_id FROM _dbl_auto_id_table
        """)
        rows = cur.fetchone()

        last_assigned_id = rows[0]

        # Get highest sibling index for specified tag parent id
        cur.execute("""
        SELECT max(tag_table.sibling_index)
            FROM tag_table
            WHERE tag_table.parent_id = """ + str(parent_tag_id))
        rows = cur.fetchone()
        sibling_index = rows[0]
        if sibling_index is None:
            # not found so start at zero
            sibling_index = 0
        else:
            # Found last used so increment index to skip to next
            sibling_index += 1

        # Add new row to tag table
        last_assigned_id += 1
        tag_id = last_assigned_id
        # (id, name, parent_id, sibling_index, type_name, media_is_ordered, can_tag_media, can_have_children, applies_to_all_in_media_stack, applies_to_all_in_version_stack)
        s = """
        INSERT INTO tag_table
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        cur.execute(s, (tag_id,
                        tag_name,
                        parent_tag_id,
                        sibling_index,
                        'user_misc',
                        0,
                        1,
                        can_have_children,
                        0,
                        0)
                        )

        # Add two new rows to metadata_string_table with blank values
        last_assigned_id += 1
        cur.execute("""
        INSERT INTO metadata_string_table
            VALUES({}, {}, '{}')""".format(last_assigned_id, 38, ''))

        # Update to tag_to_metadata_table
        cur.execute("""
        INSERT INTO tag_to_metadata_table
            VALUES({}, {})""".format(tag_id, last_assigned_id))

        last_assigned_id += 1
        cur.execute("""
        INSERT INTO metadata_string_table
            VALUES({}, {}, '{}')""".format(last_assigned_id, 43, ''))

        # Update to tag_to_metadata_table
        cur.execute("""
        INSERT INTO tag_to_metadata_table
            VALUES({}, {})""".format(tag_id, last_assigned_id))

        # Add 3 new rows to metadata_decimal_table with dummy longtitude and lattitude and zero valures
        last_assigned_id += 1
        cur.execute("""
        INSERT INTO metadata_decimal_table
            VALUES({}, {}, {})""".format(last_assigned_id, 45, -181))

        # Update to tag_to_metadata_table
        cur.execute("""
        INSERT INTO tag_to_metadata_table
            VALUES({}, {})""".format(tag_id, last_assigned_id))

        last_assigned_id += 1
        cur.execute("""
        INSERT INTO metadata_decimal_table
            VALUES({}, {}, {})""".format(last_assigned_id, 44, -91))

        # Update to tag_to_metadata_table
        cur.execute("""
        INSERT INTO tag_to_metadata_table
            VALUES({}, {})""".format(tag_id, last_assigned_id))

        last_assigned_id += 1
        cur.execute("""
        INSERT INTO metadata_decimal_table
            VALUES({}, {}, {})""".format(last_assigned_id, 46, 0))

        # Update to tag_to_metadata_table
        cur.execute("""
        INSERT INTO tag_to_metadata_table
            VALUES({}, {})""".format(tag_id, last_assigned_id))

        # Update last assigned id
        cur.execute("""
        UPDATE _dbl_auto_id_table
            SET last_assigned_id = """ + str(last_assigned_id))

        # Commit changes
        db_con.commit()

        return tag_id


def FindTagName(db_con, tag_id):
    """
    Finds a tag name given a tag_id.  Returns None if not found.
    :param db_con:  Database connection to adobe
    :param tag_id:  Int id
    :return:
    """
    with db_con:
        cur = db_con.cursor()

        # Find tag 'user_ns' first which is at the top of the treee
        cur.execute("select name from tag_table where id = {};".format(tag_id))
        row = cur.fetchone()
        if row:
            tag_name = row[0]
            return tag_name

    return None


def FindTagID(db_con, tag_name_list):
    """

    :param db_con:          The database connection
    :param tag_name_list:   A list of hierarchical tag names to search for [e.g. ['People', 'Family', 'Krantz', 'Peter Krantz']
    :return:                The tag id found or None if not found
    """
    with db_con:
        cur = db_con.cursor()

        # Find tag 'user_ns' first which is at the top of the treee
        cur.execute("""
        SELECT id
            FROM tag_table
            WHERE tag_table.name = 'user_ns'
        """)

        row = cur.fetchone()
        tag_id = row[0]

        # Now find each successive tag in the list with the specified id
        for tag in tag_name_list:
            cur.execute("""
            SELECT id
                FROM tag_table
                WHERE tag_table.name =
            """ + "'" + tag + "' AND parent_id = " + str(tag_id))
            row = cur.fetchone()
            if row:
                tag_id = row[0]
            else:
                return None
        return tag_id


def CreateAllTagLevels(db_con, tag_name_list):
    """
    Creates all levels (below the top level of People, Places, Events, Other) of the tag hierarchy that don't already exist
    :param db_con:          Open database connection
    :param tag_name_list:   Tag Hierarchy list ... e.g. ['People', 'Family', 'Krantz', 'Fiona Krantz']
    :return:                Returns count of tags added.
    """
    added_tag_count = 0

    with db_con:
        cur = db_con.cursor()

        # Find tag 'user_ns' first which is at the top of the treee
        cur.execute("""
        SELECT id
            FROM tag_table
            WHERE tag_table.name = 'user_ns'
        """)

        row = cur.fetchone()
        tag_id = row[0]

        # Now find each successive tag in the list with the specified id
        for tag in tag_name_list:
            cur.execute("""
            SELECT id, can_have_children
                FROM tag_table
                WHERE tag_table.name =
            """ + "'" + tag + "' AND parent_id = " + str(tag_id))
            row = cur.fetchone()
            current_level = tag_name_list.index(tag)
            if row:
                # Found the next level of the tag hierarchy so continue.
                tag_id = row[0]
                # If this is not a "leaf" (last tag in the hierarchy) then make sure it is set to
                # be able to have children
                if current_level < tag_name_list.__len__() - 1:
                    can_have_children = row[1]
                    if not can_have_children:
                        # This tag needs to have children but is not set to allow this so update to allow this
                        cur.execute("""
                        UPDATE tag_table
                            SET can_have_children = 1
                            WHERE id = """ + str(tag_id))
                        db_con.commit()
            else:
                # Didn't find this lvel in the hierarchy so create it if after level 1 and continue
                if current_level > 1:
                    # Found a missing element above the first level so add it
                    if current_level < (tag_name_list.__len__() - 1):
                        can_have_children = 1
                    else:
                        can_have_children = 0
                    tag_id = CreateTag(db_con, tag, tag_id, can_have_children)
                    if tag_id:
                        # Tag added so increment add count
                        added_tag_count += 1
                    else:
                        # Couldn't add tag so exit.
                        return added_tag_count
                else:
                    # Can't add this level so return the number of tags added.
                    return added_tag_count
        return added_tag_count


def FindMediaTableIDFromUNCSpec(db_con, unc_spec_filename):
    """
    Searches media_table for a file with the specified unc_spec_filename and returns the media_id of it (or None if not found)
    :param db_con               Open database connection to Adobe Elements 6.0 SQLite Catalog database file
    :param unc_spec_filename:   Full UNC filespec of file to locate [NB: use raw string literals to avoid slash problems]
    :return:                    media_id of located file or None if not found.
    """
    #
    lc_base_filename = ntpath.normcase(unc_spec_filename)
    drive, remainder = ntpath.splitdrive(lc_base_filename)
    lc_base_filename = (ntpath.basename(remainder)).lower()
    dir = str.replace(ntpath.dirname(remainder), '\\', '/')
    if dir[-1] != '/':
        # Add trailing forward slash
        dir += '/'
    with db_con:
        cur = db_con.cursor()

        # Find tag 'user_ns' first which is at the top of the treee
        query = """
        SELECT id
            FROM media_table
            WHERE filepath_search_index = "{}" AND filename_search_index = "{}";
        """.format(dir, lc_base_filename)

        cur.execute(query)

        row = cur.fetchone()
        if row:
            media_id = row[0]
        else:
            media_id = None
        return media_id


def GetTagListsForFileFromFileEXIFData(unc_spec_filename):
    """
    Returns a dictionary of EXIF data from a files
    :param unc_spec_filename:   Full UNC filespec of file to check [NB: use raw string literals to avoid slash problems]
    :return:                    Dictionary with values d['keywords'], d['rating'], d['caption'] where
        keywords:                   is the returned list of Iptc keywords found ('Iptc.Application2.Keywords') or None if not found (should also be same as 'Xmp.dc.subject' value list)
        rating:                     is a returned integer rating value
        caption:                    is a returned caption value

    """

    d = dict()

    metadata = pyexiv2.ImageMetadata(ntpath.normpath(unc_spec_filename))
    try:
        metadata.read()
    except:
        return None

    # Exmaple of changing a value in an ITCP multi-value tag.
    # Save old tag values
    key = 'Iptc.Application2.Keywords'
    try:
        tag = metadata[key]
        d['keywords'] = tag.values
    except:
        d['keywords'] = None

    # Get photo rating
    try:
        d['rating'] = metadata['Xmp.xmp.Rating'].value
    except:
        d['rating'] = None

    # Caption
    try:
        d['caption'] = metadata['Iptc.Application2.Caption'].value
    except:
        d['caption'] = None

    return d

def GetMediaThumbnailFromMediaId(media_thumb_db_con:lite.Connection, media_id:int, width:int, height:int):
    """
    Reads the adobe photoshop elements media cache sqlite database and searches for an image thumbnail
    with the specified width and height.
    :param media_thumb_db_con:  Connection to open adobe photoshop element 6 thumbnail cache database
    :param media_id:            int media id of the image to get the thumbnail of
    :param width:               int width in pixels to search for - usually 160 or 320.
    :param height:              int height in pixels to search for - usually 120 or 240.
    :return:                    QImage of thumbnail or None if not found.
    """

    try:
        with media_thumb_db_con:
            # First get the
            query = """
                SELECT
                    thumbnail_data_table.thumb_id,
                    thumbnail_data_table.thumbnail 
                FROM 
                    thumbnail_data_table, thumbnail_info_table
	            WHERE 
		            thumbnail_info_table.media_id = ? and thumbnail_info_table.width = ? and thumbnail_info_table.height = ? and thumbnail_data_table.thumb_id = thumbnail_info_table.id;
                """
            cur = media_thumb_db_con.cursor()
            cur.execute(query,(media_id, width, height))
            db_row = cur.fetchone()
            if db_row:
                (
                    thumb_id,
                    thumbnail_blob
                ) = db_row
            else:
                # Not found.
                return None

    except:
        ex = Exception("Unexpected error attempting to load thumbnail for {media_id}")
        raise ex

    # Convert blob to image
    thumbnail_qimage = QImage()
    thumbnail_qimage.loadFromData(thumbnail_blob, "JPG")

    return thumbnail_qimage

def SetFileEXIFData(unc_spec_filename, keywords, rating, caption):
    # type: (str, list, int, str) -> object
    """
    Updates EXIF data in a file with IPTC keywords and XMP subject-dc and caption and XMP rating tags
    :param unc_spec_filename:   Full UNC filespec of file to check [NB: use raw string literals to avoid slash problems]
    :param keywords:            List of keywords to replace current IPTC keywords and XMP subject-dc values
    :param rating:              Integer rating to set XMP rating
    :param caption:             Photo caption to set IPTC caption
    :return:                    True if succeeded or False if it didn't

    """
    return_val = True
    metadata = pyexiv2.ImageMetadata(ntpath.normpath(unc_spec_filename))
    try:
        metadata.read()
    except:
        return False

    key = 'Iptc.Application2.Keywords'
    try:
        tag = metadata[key]
        tag.values = keywords
    except:
        return_val = False

    key = 'Xmp.dc.subject'
    try:
        tag2 = metadata[key]
        tag2.value = keywords
    except:
        return_val = False

    # Set photo rating
    try:
        metadata['Xmp.xmp.Rating'].value = rating
    except:
        return_val = False

    # Caption
    try:
        metadata['Iptc.Application2.Caption'].value = caption
    except:
        return_val = False

    try:
        metadata.write()
    except:
        return_val = False

    return return_val

def GetTagListsForFileFromCatalog(db_con, media_id):
    """

    :rtype: list of lists
    :param db_con:      Open database connection to Adobe Elements 6.0 SQLite Catalog database file
    :param media_id:    Media id of file to get tags for
    :return:            Returns list of tag lists - e.g [[[u'People', u'Family', u'Krantz', u'Emma Krantz'],
                                                         [u'People', u'Family', u'Krantz', u'Fiona Krantz']])
    """

    tag_lists = []
    with db_con:
        cur = db_con.cursor()
        # Return the tag_id's of all the tags associated with this media_id
        query = """
        Select tag_to_media_table.tag_id
            from media_table, tag_to_media_table
            where  media_table.id = {}
            AND media_table.id = tag_to_media_table.media_id;
        """.format(media_id)

        cur.execute(query)
        rows = cur.fetchall()
        for row in rows:
            tags = GetTagHierarchyForTag(db_con, row[0])
            tag_lists.append(tags)

    return tag_lists


def GetRatingForFileFromCatalog(db_con, media_id):
    with db_con:
        cur = db_con.cursor()
        # Return the tag_id's of all the tags associated with this media_id
        query = """select metadata_integer_table.value
            from media_table, media_to_metadata_table, metadata_integer_table where 
                media_table.id = '{}' AND
                media_to_metadata_table.media_id = media_table.id AND
                metadata_integer_table.id = media_to_metadata_table.metadata_id AND metadata_integer_table.description_id = 4;
        """.format(media_id)

        cur.execute(query)
        row = cur.fetchone()

        return row[0]


def GetCaptionOfFileFromCatalog(db_con, media_id):
    with db_con:
        cur = db_con.cursor()
        # Return the tag_id's of all the tags associated with this media_id
        query = """select metadata_string_table.value
            from media_table, media_to_metadata_table, metadata_string_table where 
                media_table.id = '{}' AND
                media_to_metadata_table.media_id = media_table.id AND
                metadata_string_table.id = media_to_metadata_table.metadata_id AND metadata_string_table.description_id = 2;
        """.format(media_id)

        cur.execute(query)
        row = cur.fetchone()

        if row:
            return row[0]
        else:
            return None

def get_tag_id_of_specified_tag_name(db_con, tag_name):
    """
    Reads specified adobe elements database to retrieve the id of the specified tag name
    :param db_con:      Open connection to adobe elements catalog sqlite database
    :param tag_name:    String containing name of tag to search for
    :return:            id of tag found or None if not found
    """
    with db_con:
        query = "SELECT id FROM tag_table WHERE name = '{}';".format(tag_name)
        cur = db_con.cursor()
        cur.execute(query)
        row = cur.fetchone()
        if row:
            # Found value so return it.
            return row[0]
        else:
            return(None)


def GetTagHierarchyForTag(db_con, tag_id):
    """
    Returns a list with the name of the specified tag and all parent tags above that are its ancestors in the tag hierarchy
    :param db_con:      Open database connection to Adobe Elements 6.0 SQLite Catalog database file
    :param tag_id:      The id of the tag we're trying to create the tag hierarchy list for
    :return:            A list of tags in the hierarchy - e.g. ['People', 'Family', 'Krantz', 'Fiona Krantz']
    """

    tag_list = []

    with db_con:
        cur = db_con.cursor()

        # query = """
        #     WITH RECURSIVE
        #         parent_of(id, parent_id) AS
        #             (SELECT id, parent_id FROM tag_table),
        #         ancestor_of_person(id) AS
        #             (SELECT parent_id FROM parent_of WHERE id={0}
        #         UNION ALL
        #             SELECT parent_id FROM parent_of JOIN ancestor_of_person USING(id))
        #     SELECT tag_table.id, tag_table.parent_id, tag_table.name FROM ancestor_of_person, tag_table
        #         WHERE ancestor_of_person.id=tag_table.id and tag_table.parent_id!=0 union SELECT tag_table.id, tag_table.parent_id, tag_table.name FROM tag_table WHERE id={0}
        #         ORDER BY parent_id;
        #     """.format(tag_id)

        query = """            
        WITH RECURSIVE
                parent_of(id, parent_id, reclevel_a) AS
                    (SELECT id, parent_id, 1 FROM tag_table),
                ancestor_of_person(id, reclevel_b) AS
                    (SELECT parent_id, 1 FROM parent_of WHERE id={0}
                        UNION ALL
                            SELECT parent_id, reclevel_a+1 FROM parent_of JOIN ancestor_of_person USING(id)
                    )
            SELECT tag_table.id, tag_table.parent_id, tag_table.name, reclevel_b FROM ancestor_of_person, tag_table
                WHERE ancestor_of_person.id=tag_table.id and tag_table.parent_id!=0 
                    UNION 
                        SELECT tag_table.id, tag_table.parent_id, tag_table.name, 0 As reclevel FROM tag_table 
                            WHERE id={0}
                                ORDER BY reclevel_b DESC;
        """.format(tag_id)

        # For Miling tag_table.id = 2690

        cur.execute(query)

        rows = cur.fetchall()

        for row in rows:
            tag_list.append(row[2])

    return tag_list


def debug_print(p):
    if debug_mode:
        print(p)
    return


def CheckUpdateMetadataOfFilesInCatalog(db_con, date_taken_start_date=None, update=False):
    """
    Checks the metadate in Adobe Elements Catalog to see whether it matches the EXIF and IPTC data in the corresponding
    image files
    :param db_con:                  Open database connection to Adobe Elements 6.0 SQLite Catalog database file
    :param date_taken_start_date:   Catalog 'date taken' after which photos should start being checked (None if all should be checked)
    :param update:                  True if any image files whose metadata does not match the catalog should be updated rather than just
                                    checked
    :return:
    """
    adobe_elments_top_level_tags = {u'Places', u'Events', u'People', u'Other'}

    # Set start and end records
    start_count = 0
    max_count = 2**30

    if date_taken_start_date:
        date_msg = "taken after " + date_taken_start_date.strftime("%d/%m/%Y") + ' '
    else:
        date_msg = ''


    if update:
        u_msg = u'Update mode on - all images '+ date_msg + 'not aligned to the catalog will have their metadata updated.'
        r = MsgBox(u'WARNING ',u_msg, 1)
    else:
        u_msg = u'Update mode off - all images '+ date_msg + 'will be checked but not updated.'
        r = MsgBox(u'NOTE', u_msg, 1)

    if r == 2:
        # User cancelled.
        return

    print(u_msg)
    print("Commencing ...")

    f = open(r"E:\UP\Peter4\OneDrive\Unencrypted2\PycharmProjects\AdobeElementsSQLiteTools\logfile.csv", "a")
    mywriter = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_NONNUMERIC, lineterminator='\n')
    mywriter.writerow([time.strftime("%d/%m/%Y %H:%M:%S"), "Commencing new catalog check ..."])
    mywriter.writerow([time.strftime("%d/%m/%Y %H:%M:%S")])

    with db_con:
        cur = db_con.cursor()

        if date_taken_start_date:
            # query = """
            #     select media_table.id, media_table.full_filepath from media_table, media_to_metadata_table, metadata_date_time_table where 
            #         media_table.id = media_to_metadata_table.media_id and 
            #         media_to_metadata_table.metadata_id = metadata_date_time_table.id and 
            #         metadata_date_time_table.description_id = 8 and /* 8 = FileDateOriginal */
            #         metadata_date_time_table.value > date('{}-{:02d}-{:02d}');            
            # """.format(date_taken_start_date.year, date_taken_start_date.month, date_taken_start_date.day)

            query = """
                select id, full_filepath from 
                    (select media_table.id, media_table.full_filepath, min(metadata_date_time_table.value) as min_date
                    from media_table, media_to_metadata_table, metadata_date_time_table
                    where 
                        media_table.id = media_to_metadata_table.media_id 
                        and media_to_metadata_table.metadata_id = metadata_date_time_table.id
                    group by media_table.id)
                where min_date > '{}{:02d}{:02d}';       
            """.format(date_taken_start_date.year, date_taken_start_date.month, date_taken_start_date.day)

        else:
            query = """
                select media_table.id, media_table.full_filepath from media_table;
                """

        cur.execute(query)

        row = cur.fetchone()

        count = 0
        match_count = 0
        unreadable_file_count = 0

        while row and count < start_count:
            row = cur.fetchone()
            count += 1

        try:
            while row and count <= max_count:
                # Assume match until found otherwise
                match = True
                filname = u"C:" + row[1]
                media_id = row[0]  # FindMediaTableIDFromUNCSpec(db_con, filname)
                debug_print(u"filename: '{}'\nmedia_id: {}".format(filname, media_id))
                debug_print(u"Data from Catalog:\n")
                cat_caption = None
                cat_rating = None
                tag_lists = None

                if media_id:
                    orig_tag_lists = GetTagListsForFileFromCatalog(db_con, media_id)
                    tag_lists = list(filter(lambda x: 'Auto Face Tagging' not in x, orig_tag_lists))
                    cat_rating = GetRatingForFileFromCatalog(db_con, media_id)
                    cat_caption = GetCaptionOfFileFromCatalog(db_con, media_id)
                    debug_print(u"{}\nrating: {}\ncaption: {}".format(tag_lists, cat_rating, cat_caption))
                else:
                    debug_print(u"Filename '{}' not found.".format(filname))

                # Ignore any files thaat have extenstions of types we know we can't update.
                if ntpath.splitext(filname)[-1].lower() in {'.cr2', '.mov', '.tga', '.bmp'}:
                    unreadable_file_count += 1
                else:
                    d = GetTagListsForFileFromFileEXIFData(filname)
                    if not d:
                        unreadable_file_count += 1
                    else:
                        keywords = d['keywords']
                        rating = d['rating']
                        caption = d['caption']

                        debug_print(u"\nData from EXIF details in file:\n")
                        debug_print(u"keywords: {}\n rating: {}\n caption: {}".format(keywords, rating, caption))

                        # Check if data from Catalog is in metadata
                        cat_keywords = []
                        for tag in tag_lists:
                            if tag[0] in adobe_elments_top_level_tags:
                                sep = '|'
                                s = []
                                for t in tag:
                                    s.append(t.encode('ascii'))
                                delim_tags = sep.join(s)
                                cat_keywords.append(delim_tags)
                                if keywords and delim_tags in keywords:
                                    debug_print(u"Found metadata tag '{}' from catalog in file metadata\n".format(delim_tags))
                                else:
                                    debug_print(u"Metadata tag '{}' from catalog not found in file metadata\n".format(delim_tags))
                                    match = False

                        if cat_rating != rating or (cat_caption and not caption):
                            match = False
                        else:
                            if (cat_caption and caption) and (cat_caption != caption[0]):
                                match = False

                        if match or (not cat_rating and not cat_caption and cat_keywords == []):
                            # No catalog data to update or found a match so increment count and continue
                            debug_print(
                                u"File '{}' MATCHES".format(filname))
                            match_count += 1
                        else:
                            # Did not match and not unreadable file so try updating its metadata
                            debug_print(
                                u"File '{}' DOES NOT match".format(filname))
                            mywriter.writerow([time.strftime(u"%d/%m/%Y %H:%M:%S"), count, count - match_count, u"Updated following file with rating, caption and keywords:" if update else u"Would have updated following file with rating, caption and keywords:", filname.encode('UTF-8'), cat_rating, cat_caption, cat_keywords])

                            if update:
                                b_success = SetFileEXIFData(filname, cat_keywords, cat_rating, cat_caption)

                count += 1
                if (count % 1000) == 0:
                    print("Processed {} rows  Total matches: {}  Unreadable files: {}".format(count, match_count,
                                                                                              unreadable_file_count))
                row = cur.fetchone()
        except:
            if row:
                s = "Media ID " + str(row[0])
            else:
                s = ""
            print("Unexpected error at count {} {} {} {}:".format(count, s, sys.exc_info()[0], sys.exc_info()[1]))
            raise

        print("\n\nTotal count: {}\nTotal matches: {}\nUnreadable files: {}".format(count, match_count,
                                                                                    unreadable_file_count))

    f.close()

    return


def MsgBox(title, text, style=1):
    """
    Simple message box
    :param title:
    :param text:
    :param style:
        0 : OK
        1 : OK | Cancel
        2 : Abort | Retry | Ignore
        3 : Yes | No | Cancel
        4 : Yes | No
        5 : Retry | No
        6 : Cancel | Try Again | Continue
    :return:
    """
    return ctypes.windll.user32.MessageBoxW(0, text, title, style)


def main():
    # my code here

    con = lite.connect(r'C:\ProgramData\Adobe\Photoshop Elements\Catalogs\My Catalog\catalog.psedb')

    # print(lite.version)
    # with con:
    #     cur = con.cursor()
    #     cur.execute("""
    #     Select tag_to_media_table.tag_id, tag_table.name
    #         from media_table, tag_to_media_table, tag_table
    #         where  media_table.full_filepath = '/Users/Peter4/Pictures/My Pictures/Kodak Pictures/2003-02-08/100_0254.JPG'
    #         AND media_table.id = tag_to_media_table.media_id
    #         AND tag_to_media_table.tag_id = tag_table.id
    #     """)
    #     rows = cur.fetchall()
    #     for row in rows:
    #         tags = GetTagHierarchyForTag(con, row[0])
    #         print(tags)

    # print(CreateTag(con, "test2", FindTagID(con, ['People', 'Family'])))
    ## print("Tags added: {}".format(CreateAllTagLevels(con, ['People', 'Family', 'Krantz', 'Peter Krantz', 'Below Peter Krantz'])))
    # filname = r"C:\Users\krant\Pictures\Arachnoid Sisters - orig.jpg"

    # filname = r"C:\Users\Peter4\Pictures\2015 07 24\IMG_0254.jpg"
    # print("File '{}' has id {}".format(filname, FindMediaTableIDFromUNCSpec(con, filname)))
    # print("FindTagID() {}", FindTagID(con, ['People', 'Family', 'Krantz', 'Fiona Krantz']))
    # filname = r'C:/Users/Peter4/Pictures/My Pictures/2012 09 30/IMG_5503.JPG'
    # print("filename: '{}'\n".format(filname))
    # print("Data from Catalog:\n")
    # media_id = FindMediaTableIDFromUNCSpec(con, filname)
    # if media_id:
    #     tag_lists = GetTagListsForFileFromCatalog(con, media_id)
    #     rating = GetRatingForFileFromCatalog(con, media_id)
    #     print("{}\n rating: {}\n".format(tag_lists, rating))
    # else:
    #     print("Filename '{}' not found.".format(filname))
    #
    #
    # d = GetTagListsForFileFromFileEXIFData(filname)
    # keywords = d['keywords']
    # rating = d['rating']
    # caption = d['caption']
    #
    # print("\nData from EXIF details in file:\n")
    # print("keywords: {}\n rating: {}\n caption: {}".format(keywords, rating, caption))

    filname = r"E:\UP\Peter4\Desktop\IMG_0255.jpg"
    keywords = ["this is", "a test", "of adding", "some keywords to the file"]
    rating = 4
    caption = "This is a test"
    # SetFileEXIFData(filname, keywords, rating, caption)

    # CheckUpdateMetadataOfFilesInCatalog(con, datetime.datetime(2018,1,30), update=True)
    CheckUpdateMetadataOfFilesInCatalog(con, date_taken_start_date=datetime.datetime(1990,1,1), update=True)

    con.close()


if __name__ == "__main__":
    main()
    exit()
