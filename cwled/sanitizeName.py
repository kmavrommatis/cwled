import re

class sanitize(object):
    '''
    class to sanitize a string
    Based on the configuratio it returns the string

    configuration options:
    underscore:  "any string" will become "any_string"
    dash:  "any string" will become "any-string"
    UpperCamelCase: "any string" will become "AnyString"
    lowerCamelCase: "any string" will become "anyString"
    keepAlNum: will keep only a-Z, 0-9. Any other character will be replaced by space "@ny_String!" will become " ny String "
    '''

    def __init__(self, text=None):
        '''
        initialize the class
        
        '''
        self.input_text=str(text)
        self.text=text
        self.rep=[]
        
        #self.setConfiguration(configuration)
    
    def keepAlphaNum(self):
        '''
        remove unwanted characters i.e. non alphanumeric
        ''' 
        self.rep.append('keepAlNum()')
        self.text = re.sub('[^0-9a-zA-Z]+', " ", self.input_text)
        return self
        # return self.text


    def camelCase(self):
        self.text = re.sub(r"(_|-)+", " ", self.text).title().replace(" ", "")
        
        return self
        # return self.text
    
    def UpperCamelCase(self):
        self.rep.append('UpperCamelCase()')
        self.camelCase()
        self.text= ''.join([self.text[0].upper(), self.text[1:]])
        # return self.text
        return self

    def lowerCamelCase(self):
        self.rep.append('LowerCamelCase()')
        self.camelCase()
        self.text= ''.join([self.text[0].lower(), self.text[1:]])
        # return self.text
        return self
    
    def underscore(self):
        self.rep.append('underscore()')
        self.text = re.sub(r"(_|-)+", " ", self.text).replace(" ", "_")
        # return self.text
        return self

    def dash(self):
        self.rep.append('dash()')
        self.text = re.sub(r"(_|-)+", " ", self.text).replace(" ", "-")
        # return self.text
        return self

    
    def __str__(self):
        return self.text
    
    def __repr__(self):
        return f"sanitize({self.input_text}).{'.'.join(self.rep)}"
    


if __name__ == "__main__":
    print(f"Testing sanitization")
    test="This is a text"
    print(f"Before {test}")
    s=sanitize(test).underscore()
    print(f"Text undrescore: {test} becomes : {s}")
    s=sanitize(test).lowerCamelCase()
    print(f"Text lowerCamelCase: {test} becomes : {s}")
    s=sanitize(test).UpperCamelCase()
    print(f"Text UpperCamelCase: {test} becomes : {s}")
    s=sanitize(test).underscore()
    print(f"Text underscore: {test} becomes : {s}")
    s=sanitize(test).dash()
    print(f"Text dash: {test} becomes : {s}")
    test="Th!s_is @ text"
    s=sanitize(test).keepAlphaNum()
    print(f"Text keepAlNum: {test} becomes : {s}")

    s=sanitize(test).keepAlNum().underscore()
    print(f"Text keepAlNum: {test} becomes : {s}")

    