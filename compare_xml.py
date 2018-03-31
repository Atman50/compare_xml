#!/usr/bin/python
"""
Copyright 2018, Adam Taylor

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

====================================================================================================
Compare XML using a "unique path-ing" concept.
====================================================================================================
The idea of this class is to decompose the XML into unique "paths" - that are constructed by taking an
(hopefully unique) attribute or in lieu of that the text of a element. This removes the index values which
makes the comparison resilient to ordering issues (the pathing removes the [x] array references and attempts
to make path unique using attributes and/or text values). This is not very pretty but does the job quickly
and for the case it was designed for seems to catch all the relevant cases.

Using a unique path tries to pull an attribute name or the text of the lxml._Element into a translated XML path
for the element. The unique path element is either the first value of the attribute that is matched first in
the special_attribs list (passed during construction or XMLCompare), or if no match, the lxml._Element.text
value (None is ok)

A unique path may have many solutions in some cases. Take for example the following:
    ...
    <Elem1>
       <Elem2 name="Character">
          <Elem3>backslash</Elem3>
       </Elem2>
       <Elem2 name="Character">
          <Elem3>colon</Elem3>
       </Elem2>
       <Elem2 name="Character">
          <Elem3>tab</Elem3>
       </Elem2>
    <Elem1>
    ...
There is one unique path (using name as the "unique-ifier"): .../Elem1/Elem2Character. However there are three
elements: .../Elem1/Elem2[0], .../Elem1/Elem2[1], and .../Elem1/Elem2[2]. Hence, the resultant path dictionary
generated always returns a list of elements: Any unique path represented by more than a single WrappedElement
means the path could not be made unique.

A good way to determine the list of special_attribs to use is to run successive tests calling XMLUniquePath for
a file (etree._ElementTree). After each run dump out the dictionary values for XMLUniquePath._paths; any
WrappedElement lists that have more than one element is a non-unique entry. You can print out the etree_Element
attributes to look for a uniqueness candidate. If none exists, which is reasonable, then matching can be difficult
between files that have large ordering differences. However, if the XML files are somewhat similar, the sourceline
might give some more information.

As stated previously, this difference engine works well with the problem it was written to solve and probably
doesn't solve all XML differencing problems.
"""

import io

from lxml import etree
from typing import Type, TypeVar

T_XMLCompare = TypeVar('T_XMLCompare', bound='XMLCompare')


class WrappedElement(object):
    """The WrappedElement is a handy class so that we can use set operations and bare comparison on etree._Elements
    """

    def __init__(self, element: etree._Element):
        self.element = element

    def __eq__(self, other):
        if isinstance(self, other.__class__):
            return self.element.attrib == other.element.attrib and self.element.text == other.element.text
        return False

    def __hash__(self):
        return hash(tuple(self.element.attrib.items() + [self.element.text]))


class XMLUniquePath(object):
    """This class consumes an lxml.etree._ElementTree and converts it into a dictionary of "unique" paths to
    the elements they represent.
    """

    def __init__(self, root: etree._ElementTree, special_attribs: list = [], max_text_len: int = 80):
        """The unique path is created at construction
        Keyword Arguments:
        xml: etree._ElementTree -- the xml tree to "uniquify"
        special_attribs: list   -- (default []) the special attributes to look for (see _create_path_tree)
        max_text_len: int       -- (default 80) the maximum length for unique keys (see _create_path_tree)
        """
        self.root = root
        self._special_attribs = special_attribs
        self._max_text_len = max_text_len
        self._create_path_tree()

    def _replace_trans(self, path: str) -> str:
        """Take a string and the translation table and replace the biggest substring found in translations

        Keyword Arguments:
        trans_table: dict -- the translation dictionary
        path: str         -- the path to translate

        return: A string that is the translation, if any exists. Otherwise just returns untranslated path."""
        # Keep looking for the path lopping off the last /xxxxx value
        if len(self._trans_table) == 0:
            return path
        new_path = path
        while len(new_path) > 0:
            if new_path in self._trans_table:
                break
            back_one = new_path.rfind('/')
            if back_one <= 0:
                return path
            new_path = new_path[:back_one]
        # Got a translation. We need to replace the new_path in path with the translation
        return path.replace(new_path, self._trans_table[new_path])

    def _create_path_tree(self):
        """The idea here is to create a "unique" (and predictable) path to every element we need to compare

        Translate the lxml._ElementTree.getpath into a path based on either the tag's matching special_attribs
        or the text of the tag (limited by max_text_len). Non-unique path construction does happend. The algorithm
        is for each etree._Element in the document:
            1. see if there is a "special attribute" match, if so use the text for uniqueness
            2. if no special attribute match, then use the text of the tag if not None
            3. sanitize the uniqueness string - no carriage returns or forward slashes (used for path comprehension)
            4. Limit uniqueness string
            5. Use the translation on the element's parent path
            6. Add to the parent's translation a '/' + the_element(tag) + uniqueness string
            7. Add a new translation for this etree._Element => translation string (unique path)
            8. Add a new paths entry for this translation string (unique path) => WrappedElement list
        """
        self.paths = {}
        self._trans_table = {}
        for elem in self.root.iter():
            unique_str = ''
            for key in self._special_attribs:                                       # 1
                if key in elem.attrib:
                    unique_str = elem.attrib[key]
                    break
            if unique_str == '' and elem.text is not None and len(elem.text) > 0:   # 2
                unique_str = elem.text
            # Now sanitize the string - no \n no / and limit length
            unique_str = unique_str.replace('\n', '').replace('/', '')              # 3
            if len(unique_str) > self._max_text_len:                                # 4
                unique_str = unique_str[:self._max_text_len - 1]
            parent_path = self._replace_trans('' if elem.getparent() is None        # 5
                                              else self.root.getpath(elem.getparent()))
            translated_path = parent_path + '/' + elem.tag + unique_str             # 6
            self._trans_table[self.root.getpath(elem)] = translated_path            # 7
            if translated_path in self.paths:                                       # 8
                # Non unique!
                self.paths[translated_path].append(WrappedElement(elem))
            else:
                self.paths[translated_path] = [WrappedElement(elem)]


class XMLCompare(object):
    """
    The _create_path_tree decomposes the XML into these "unique" paths (the key) and the etree._Element they "solve" to as
    the value.

    The diff_items instance variable is the detailed results from the _compare method
    """

    def __init__(self, root1: etree._ElementTree, root2: etree._ElementTree,
                 special_attribs: list = [], max_text_len: int = 80):
        """Generate the differences between two XML element trees (lxml.etree._ElementTree)

        Keyword Arguments:
        root1: etree._ElementTree -- the root of document 1
        root2: etree._ElementTree -- the root of document 2
        special_attribs: list     -- (default []) the special attributes to look for (see _create_path_tree)
        max_text_len: int         -- (default 80) the maximum length for unique keys (see _create_path_tree)
        """
        self.diff_items = {}
        self._paths1 = XMLUniquePath(root1, special_attribs=special_attribs, max_text_len=max_text_len)
        self._paths2 = XMLUniquePath(root2, special_attribs=special_attribs, max_text_len=max_text_len)
        self._compare()

    @property
    def the_same(self):
        """An easy way to see if the comparison was the same
        """
        return len(self.diff_items) == 0

    def _compare(self):
        """Compares the two documents. Called at constuction

        Create the path structure, the build self._diff_item.
        self._diff_item will contain:
            1. All unique paths found in root1 that are not in root2
            2. All unique paths found in root2 that are not in root1
            3. For all unique paths in common, add if the Element list differs between root1 and root2
        """
        paths1_set = set(self._paths1.paths.keys())
        paths2_set = set(self._paths2.paths.keys())
        # Get all the elements in root1 that are not in root2
        for key in paths1_set - paths2_set:
            self.diff_items[key] = {'root1': self._paths1.paths[key]}
        # Get all the elements in root2 that are not in root1
        for key in paths2_set - paths1_set:
            self.diff_items[key] = {'root2': self._paths2.paths[key]}
        # Now compare the values of the shared paths (appear in both root1 and root2)
        for key in paths1_set & paths2_set:
            if set(self._paths1.paths[key]) != set(self._paths2.paths[key]):
                self.diff_items[key] = {'root1': self._paths1.paths[key], 'root2': self._paths2.paths[key]}

    def get_diffs_as_string(self) -> str:
        """A handy method to self.diff_items dictionary in a human readable format
        return: a string that is the difference, or the empty string if no difference
        """
        if self.the_same:
            return ''
        max_key_len = max([len(x) for x in self.diff_items.keys()])

        with io.StringIO() as output:
            output.write('Different items\n')
            for k, diff_info_dict in self.diff_items.items():
                output.write('{:=^{width}}\n{}\n'.format('', k, width=max_key_len + 8))
                for root in 'root1 root2'.split():
                    if root in diff_info_dict:
                        output.write('  {}\n'.format(root))
                        for wrapped_elem in diff_info_dict[root]:
                            elem = wrapped_elem.element
                            output.write('    Line {}:\n'.format(elem.sourceline))
                            output.write('            Path = {}\n'.format(self._paths1.root.getpath(elem) if root == 'root1' else self._paths2.root.getpath(elem)))
                            if len(elem.attrib) > 0:
                                output.write('      Attributes = {}\n'.format(elem.attrib))
                            if elem.text:
                                output.write('            Text = {}\n'.format(elem.text))
            return output.getvalue()

    @classmethod
    def main(cls: Type[T_XMLCompare]) -> T_XMLCompare:
        """Command line for XMLCompare

        return: a newly made XMLCompare
        """
        from argparse import ArgumentParser
        # These are my test case special attributes. Yours may be different
        default_special_attribs = 'name simpleValue os value collectionName methodContext identity interfaceType'.split()
        parser = ArgumentParser(description='XMLCompare utility')
        parser.add_argument('-v', '--verbose', action='store_true', help='Turn on verbose output')
        parser.add_argument('-m', '--max-text-len', type=int, default=80,
                            help='The maximum amount of text to use for uniqueness. Default = 80')
        parser.add_argument('-a', '--attribute', type=str, nargs='*',
                            help='The attributes to use for "uniqueness". The default list is: {}'.format(', '.join(default_special_attribs)))
        parser.add_argument('xml_file_1', help='File 1 to compare')
        parser.add_argument('xml_file_2', help='File 2 to compare')
        args = parser.parse_args()
        with open(args.xml_file_1, 'r') as f:
            xml1 = etree.fromstring(f.read(), etree.XMLParser(remove_blank_text=True, remove_comments=True)).getroottree()
        with open(args.xml_file_2, 'r') as f:
            xml2 = etree.fromstring(f.read(), etree.XMLParser(remove_blank_text=True, remove_comments=True)).getroottree()
        return XMLCompare(xml1, xml2,
                          special_attribs=default_special_attribs if args.attribute is None else args.attribute,
                          max_text_len=args.max_text_len)


if __name__ == '__main__':
    xml_compare = XMLCompare.main()
    if not xml_compare.the_same:
        print(xml_compare.get_diffs_as_string(), end='')
